"""Arm kinematics, IK and joint-space planning for the MuJoCo PyRep shim.

The Panda chain is re-expressed as a pure-numpy product of fixed transforms
and z-axis joint rotations taken straight from the compiled MuJoCo model, so
FK/IK can be batched over many seeds without touching MjData.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Sequence

import numpy as np


def quat_wxyz_to_mat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_quat_xyzw(Rm):
    m = Rm
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=float)
    return q / np.linalg.norm(q)


def quat_xyzw_to_mat(q):
    x, y, z, w = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return quat_wxyz_to_mat([w, x, y, z])


def rot_log(Rm):
    """Axis-angle vector of a rotation matrix (batched over leading dims)."""
    tr = np.clip((np.trace(Rm, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)
    ang = np.arccos(tr)
    v = np.stack([Rm[..., 2, 1] - Rm[..., 1, 2],
                  Rm[..., 0, 2] - Rm[..., 2, 0],
                  Rm[..., 1, 0] - Rm[..., 0, 1]], axis=-1)
    s = np.sin(ang)
    small = s < 1e-6
    factor = np.where(small, 0.5, ang / (2.0 * np.where(small, 1.0, s)))
    out = v * factor[..., None]
    # Near pi the formula above degrades; fall back to the diagonal axis.
    near_pi = ang > np.pi - 1e-3
    if np.any(near_pi):
        Rn = Rm[near_pi]
        diag = np.clip((np.diagonal(Rn, axis1=-2, axis2=-1) + 1.0) / 2.0, 0.0, None)
        axis = np.sqrt(diag)
        axis[..., 1] *= np.where(Rn[..., 0, 1] + Rn[..., 1, 0] < 0, -1, 1)
        axis[..., 2] *= np.where(Rn[..., 0, 2] + Rn[..., 2, 0] < 0, -1, 1)
        axis /= np.maximum(np.linalg.norm(axis, axis=-1, keepdims=True), 1e-9)
        out[near_pi] = axis * ang[near_pi][..., None]
    return out


def limit_margin(Q, lows, highs):
    """Smallest normalised distance to a joint limit (0 at a limit, 0.5 at mid-range)."""
    rng = np.maximum(np.asarray(highs) - np.asarray(lows), 1e-6)
    return np.min(np.minimum(Q - lows, highs - Q) / rng, axis=-1)


class ArmChain:
    """FK/Jacobian for a serial chain of z-axis revolute joints."""

    def __init__(self, base_T: np.ndarray, links: List[np.ndarray], refs: Sequence[float],
                 tip_T: np.ndarray, lows: Sequence[float], highs: Sequence[float]):
        self.base_T = base_T          # world -> body of joint 1 (at ref)
        self.links = links            # body(joint i) -> body(joint i+1), fixed
        self.refs = np.asarray(refs, dtype=float)
        self.tip_T = tip_T            # body(joint n) -> tip
        self.lows = np.asarray(lows, dtype=float)
        self.highs = np.asarray(highs, dtype=float)
        self.n = len(refs)

    @staticmethod
    def _rz(theta):
        c, s = np.cos(theta), np.sin(theta)
        T = np.zeros(theta.shape + (4, 4))
        T[..., 0, 0] = c
        T[..., 0, 1] = -s
        T[..., 1, 0] = s
        T[..., 1, 1] = c
        T[..., 2, 2] = 1
        T[..., 3, 3] = 1
        return T

    def fk_all(self, Q):
        """Q: (N, n). Returns tip transforms (N,4,4), joint origins (N,n,3), joint axes (N,n,3)."""
        Q = np.atleast_2d(Q)
        N = Q.shape[0]
        T = np.broadcast_to(self.base_T, (N, 4, 4)).copy()
        origins = np.zeros((N, self.n, 3))
        axes = np.zeros((N, self.n, 3))
        for i in range(self.n):
            origins[:, i] = T[:, :3, 3]
            axes[:, i] = T[:, :3, 2]
            T = T @ self._rz(Q[:, i] - self.refs[i])
            if i < self.n - 1:
                T = T @ self.links[i]
        T = T @ self.tip_T
        return T, origins, axes

    def fk(self, q):
        T, _, _ = self.fk_all(np.asarray(q, dtype=float)[None])
        return T[0]

    def jacobian(self, Q):
        T, o, a = self.fk_all(Q)
        p = T[:, None, :3, 3]
        Jv = np.cross(a, p - o)
        J = np.concatenate([Jv, a], axis=-1)  # (N, n, 6)
        return T, np.transpose(J, (0, 2, 1))  # (N, 6, n)

    def pose_error(self, T, target_T):
        ep = target_T[:3, 3] - T[..., :3, 3]
        Rerr = target_T[:3, :3] @ np.swapaxes(T[..., :3, :3], -1, -2)
        er = rot_log(Rerr)
        return np.concatenate([ep, er], axis=-1)

    def solve(self, Q0, target_T, iters=80, pos_tol=2e-4, rot_tol=2e-3, damping=0.02,
              max_step=0.3, lows=None, highs=None):
        """Batched damped-least-squares IK. Returns (Q, converged_mask, err_norms)."""
        lows = np.asarray(self.lows if lows is None else lows, dtype=float)
        highs = np.asarray(self.highs if highs is None else highs, dtype=float)
        Q = np.array(np.atleast_2d(Q0), dtype=float)
        lam2 = damping ** 2
        conv = np.zeros(len(Q), dtype=bool)
        eye6 = np.eye(6)
        for _ in range(iters):
            T, J = self.jacobian(Q)
            e = self.pose_error(T, target_T)
            pe = np.linalg.norm(e[:, :3], axis=1)
            re = np.linalg.norm(e[:, 3:], axis=1)
            conv = (pe < pos_tol) & (re < rot_tol)
            if conv.all():
                break
            JJt = J @ np.swapaxes(J, 1, 2) + lam2 * eye6
            dq = (np.swapaxes(J, 1, 2) @ np.linalg.solve(JJt, e[..., None]))[..., 0]
            nrm = np.max(np.abs(dq), axis=1, keepdims=True)
            dq = dq * np.minimum(1.0, max_step / np.maximum(nrm, 1e-12))
            dq[conv] = 0.0
            Q = np.clip(Q + dq, lows, highs)
        T = self.fk_all(Q)[0]
        e = self.pose_error(T, target_T)
        pe = np.linalg.norm(e[:, :3], axis=1)
        re = np.linalg.norm(e[:, 3:], axis=1)
        conv = (pe < pos_tol) & (re < rot_tol)
        return Q, conv, pe + re


def interpolate_pose(T0, T1, t):
    """Linear position / geodesic orientation interpolation."""
    p = (1 - t) * T0[:3, 3] + t * T1[:3, 3]
    Rrel = T0[:3, :3].T @ T1[:3, :3]
    w = rot_log(Rrel[None])[0] * t
    ang = np.linalg.norm(w)
    if ang < 1e-12:
        Rw = np.eye(3)
    else:
        k = w / ang
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        Rw = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * (K @ K)
    T = np.eye(4)
    T[:3, :3] = T0[:3, :3] @ Rw
    T[:3, 3] = p
    return T


def linear_ik_path(chain: ArmChain, q_start, target_T, steps: int,
                   collision_fn: Optional[Callable[[np.ndarray], bool]] = None,
                   lows=None, highs=None) -> Optional[np.ndarray]:
    """Cartesian straight-line path (CoppeliaSim generateIkPath semantics)."""
    steps = max(2, int(steps))
    q = np.asarray(q_start, dtype=float)
    T0 = chain.fk(q)
    out = [q.copy()]
    for k in range(1, steps):
        t = k / (steps - 1)
        Tk = interpolate_pose(T0, target_T, t)
        final = k == steps - 1
        Q, conv, _ = chain.solve(q[None], Tk, iters=60 if final else 25,
                                 pos_tol=2e-4 if final else 1e-3,
                                 rot_tol=2e-3 if final else 1e-2,
                                 lows=lows, highs=highs)
        if not conv[0]:
            return None
        qn = Q[0]
        # Reject IK flips: consecutive waypoints must stay close in joint space.
        if np.max(np.abs(qn - q)) > 0.35:
            return None
        if collision_fn is not None and collision_fn(qn):
            return None
        out.append(qn.copy())
        q = qn
    return np.array(out)


def rrt_connect(q_start, goals: List[np.ndarray], lows, highs,
                collision_fn: Optional[Callable[[np.ndarray], bool]],
                max_time_s=2.0, step=0.12, resolution=0.04, rng=None) -> Optional[np.ndarray]:
    """Joint-space RRT-Connect to any of `goals`, with shortcut smoothing."""
    rng = rng or np.random.default_rng()
    lows = np.asarray(lows, dtype=float)
    highs = np.asarray(highs, dtype=float)

    def coll(q):
        return collision_fn is not None and collision_fn(q)

    def edge_free(a, b):
        n = int(np.ceil(np.max(np.abs(b - a)) / resolution))
        for i in range(1, n + 1):
            if coll(a + (b - a) * (i / n)):
                return False
        return True

    q_start = np.asarray(q_start, dtype=float)
    goals = [np.asarray(g, dtype=float) for g in goals if not coll(np.asarray(g, dtype=float))]
    if not goals or coll(q_start):
        return None
    for g in goals:
        if edge_free(q_start, g):
            return np.array([q_start, g])

    t_end = time.monotonic() + max_time_s
    tree_a = [(q_start, -1)]
    tree_b = [(g, -1) for g in goals]
    a_is_start = True

    def nearest(tree, q):
        d = [np.linalg.norm(n[0] - q) for n in tree]
        return int(np.argmin(d))

    def extend(tree, q_target):
        i = nearest(tree, q_target)
        q_near = tree[i][0]
        d = q_target - q_near
        dist = np.linalg.norm(d)
        q_new = q_target if dist <= step else q_near + d / dist * step
        if edge_free(q_near, q_new):
            tree.append((q_new, i))
            return len(tree) - 1, np.allclose(q_new, q_target)
        return None, False

    def path_to_root(tree, idx):
        out = []
        while idx >= 0:
            out.append(tree[idx][0])
            idx = tree[idx][1]
        return out

    while time.monotonic() < t_end:
        q_rand = rng.uniform(lows, highs)
        idx_a, _ = extend(tree_a, q_rand)
        if idx_a is not None:
            q_new = tree_a[idx_a][0]
            # Connect tree_b greedily towards q_new.
            while True:
                idx_b, reached = extend(tree_b, q_new)
                if idx_b is None:
                    break
                if reached:
                    pa = path_to_root(tree_a, idx_a)[::-1]
                    pb = path_to_root(tree_b, idx_b)
                    path = pa + pb[1:]
                    if not a_is_start:
                        path = path[::-1]
                    return _shortcut(np.array(path), edge_free, rng)
        tree_a, tree_b = tree_b, tree_a
        a_is_start = not a_is_start
    return None


def _shortcut(path, edge_free, rng, iters=60):
    path = list(path)
    for _ in range(iters):
        if len(path) <= 2:
            break
        i, j = sorted(rng.choice(len(path), 2, replace=False))
        if j - i < 2:
            continue
        if edge_free(path[i], path[j]):
            path = path[:i + 1] + path[j:]
    # Densify so executors that step through waypoints move smoothly.
    dense = [path[0]]
    for a, b in zip(path[:-1], path[1:]):
        n = max(1, int(np.ceil(np.max(np.abs(b - a)) / 0.05)))
        for k in range(1, n + 1):
            dense.append(a + (b - a) * (k / n))
    return np.array(dense)
