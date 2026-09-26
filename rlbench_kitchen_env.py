# rlbench_kitchen_env.py
import os
import time
import numpy as np
import sim_backend  # noqa: F401  (SIM_BACKEND=mujoco selects the MuJoCo port)
from pyrep import PyRep
from pyrep.robots.arms.panda import Panda
from pyrep.robots.end_effectors.panda_gripper import PandaGripper
from pyrep.objects.shape import Shape
from pyrep.objects.vision_sensor import VisionSensor
from pyrep.const import ConfigurationPathAlgorithms
from pyrep.backend import sim
from llm_pipeline.region_aliases import (
    
    BOX_LID_TOP_REGION,
    BOX_STORAGE_REGION,
    CUPBOARD_TARGET_REGIONS,
    RegionAliasMap,
    normalize_region_name,
)

DEFAULT_SCENE_FILE = os.path.join(os.path.dirname(__file__), "task1_variation1.ttt")
SCENE_FILE = os.environ.get("KITCHEN_SCENE_FILE", DEFAULT_SCENE_FILE)
MUG_PLACEMENT_MIN_SAMPLE_Z = float(os.environ.get("MUG_PLACEMENT_MIN_SAMPLE_Z", "0.8"))

def _quat_xyzw_from_matrix(R):
    """Rotation matrix -> quaternion (x, y, z, w)."""
    R = np.asarray(R, dtype=float)
    t = np.trace(R)
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        w, x, y, z = 0.25 / s, (R[2, 1] - R[1, 2]) * s, (R[0, 2] - R[2, 0]) * s, (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    q = np.array([x, y, z, w])
    return (q / np.linalg.norm(q)).tolist()


def side_grasp_quat(approach_yaw, gamma):
    """Tip orientation of a horizontal side grasp: the tip z axis (approach) points along
    ``approach_yaw`` in the horizontal plane, and the fingers close horizontally (the tip x
    axis, the closing axis, is horizontal and perpendicular to the approach). ``gamma`` = +-pi/2
    picks which way round; the pick and the cupboard place of one object use the same gamma,
    so the object is not rolled over between them. R = Rz(yaw) Ry(pi/2) Rz(gamma)."""
    cz, sz = np.cos(approach_yaw), np.sin(approach_yaw)
    Rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    Ry = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    cg, sg = np.cos(gamma), np.sin(gamma)
    Rg = np.array([[cg, -sg, 0.0], [sg, cg, 0.0], [0.0, 0.0, 1.0]])
    return _quat_xyzw_from_matrix(Rz @ Ry @ Rg)


class NoFreePlacement(RuntimeError):
    """A region has no spot where the object's footprint is clear of the other objects."""


class RLBenchKitchenEnv:
    def __init__(self, headless=True):
        self.pr = PyRep()
        self.pr.launch(SCENE_FILE, headless=headless)
        self.pr.start()

        # ---- robot ----
        self.robot = Panda()
        # self.arm_joints = self.robot.get_joints() # Panda object doesn't expose get_joints directly like this
        self.gripper = PandaGripper()
        # Store the initial joint configuration as "home" for retreating
        self.home_conf = self.robot.get_joint_positions()
        
        # ---- cameras ----
        self.cams = {
            'left': VisionSensor('cam_over_shoulder_left'),
            'right': VisionSensor('cam_over_shoulder_right'),
            'overhead': VisionSensor('cam_overhead'),
            'wrist': VisionSensor('cam_wrist'),
            'front': VisionSensor('cam_front'),
        }
        
        # Configure cameras for recording
        for name, cam in self.cams.items():
            cam.set_explicit_handling(1) # We will manually trigger capture
            cam.set_resolution([640, 480]) # Set resolution
            # cam.set_render_mode(VisionSensor.RenderMode.OPENGL3) # Ensure OpenGL rendering
            
        # Set a starting configuration if needed
        # self.robot.set_joint_positions([...])

        # Directory for saving/loading named joint configurations
        import os as _os
        self.state_dir = _os.path.join(_os.path.dirname(__file__), "data_states")
        _os.makedirs(self.state_dir, exist_ok=True)

        # ---- objects (FIX NAMES TO MATCH .ttt SCENE) ----
        self.target_region_name = None # Global context for pick strategy

        def _safe_shape(name):
            try:
                return Shape(name)
            except Exception:
                return None

        self.mug_cupboard = _safe_shape('mug3')
        self.mug_box = _safe_shape('mug2')
        self.mug_table = _safe_shape('mug1')
        self.mug_inside_box = _safe_shape('mug4')

        self.bottle = _safe_shape('mustard')
        self.can = _safe_shape('soup')
        self.tin = _safe_shape('spam')
        self.food_box = _safe_shape('sugar')
        self.cereal = _safe_shape('crackers')

        self.table = _safe_shape('diningTable')
        self.box = _safe_shape('box_base')
        self.cupboard = _safe_shape('cupboard')

        if self.box is not None:
            try:
                self.box.set_dynamic(False)
            except Exception:
                pass

        self.box_lid = _safe_shape('box_lid') or self.box

        self.groceries_boundary = _safe_shape('groceries_boundary')
        self.placement_boundary = _safe_shape('placement_boundary')
        self.cupboard_boundary = _safe_shape('cupboard_boundary')
        self.box_boundary = _safe_shape('box_boundary')
        self.cupboard_boundary_top = _safe_shape('cupboard_boundary_top')

        # Keep boundary objects as-is from the scene. Do not remap to other regions.
        # This preserves your edited boundary dimensions exactly.

        if self.table is None:
            print("Warning: 'diningTable' not found in scene.")
        if self.box is None:
            print("Warning: 'box_base' not found in scene.")
        if self.cupboard is None:
            print("Warning: 'cupboard' not found in scene.")
        if self.groceries_boundary is None:
            print("Warning: 'groceries_boundary' not found in scene.")
        if self.placement_boundary is None:
            print("Warning: 'placement_boundary' not found in scene.")
        if self.cupboard_boundary is None:
            print("Warning: 'cupboard_boundary' not found in scene.")
        if self.box_boundary is None:
            print("Warning: 'box_boundary' not found in scene.")
        if self.cupboard_boundary_top is None:
            print("Warning: 'cupboard_boundary_top' not found in scene.")
        if self.mug_cupboard is None:
            print("Warning: 'mug3' (cupboard mug) not found in scene.")
        if self.mug_box is None:
            print("Warning: 'mug2' (box mug) not found in scene.")

        # Map region names to objects (only keep available regions)
        self.regions = RegionAliasMap()
        if self.table is not None:
            self.regions['table'] = self.table
        if self.groceries_boundary is not None:
            self.regions['groceries_boundary'] = self.groceries_boundary
        if self.placement_boundary is not None:
            self.regions['placement_boundary'] = self.placement_boundary
        if self.cupboard_boundary is not None:
            self.regions['cupboard_lower'] = self.cupboard_boundary
        if self.box_boundary is not None:
            self.regions[BOX_STORAGE_REGION] = self.box_boundary
        if self.box_lid is not None:
            self.regions[BOX_LID_TOP_REGION] = self.box_lid

        self.name_to_obj = {}

        def _register(name, obj):
            if obj is not None:
                self.name_to_obj[name] = obj

        _register('mug_cupboard', self.mug_cupboard)
        _register('mug_box', self.mug_box)
        _register('mug_table', self.mug_table)
        _register('mug_inside_box', self.mug_inside_box)
        _register('bottle', self.bottle)
        _register('can', self.can)
        _register('tin', self.tin)
        _register('food_box', self.food_box)
        _register('cereal', self.cereal)
        _register('can_of_beans', self.can)
        _register('can_of_beans_box', self.can)
        _register('mustard', self.bottle)
        _register('mustard_box', self.bottle)
        _register('spam', self.tin)
        _register('spam_box', self.tin)
        _register('sugar', self.food_box)
        _register('crackers', self.cereal)
        _register('box_lid', self.box_lid)
        _register('box_base', self.box)
        _register(BOX_STORAGE_REGION, self.box_boundary)
        _register(BOX_LID_TOP_REGION, self.box_lid)
        _register('cupboard_lower', self.cupboard_boundary)
        # Mug aliases
        _register('mug1', self.mug_table)
        _register('mug2', self.mug_box)
        _register('mug3', self.mug_cupboard)
        _register('mug4', self.mug_inside_box)

        # Track placed positions to avoid overlapping placements
        self.placed_positions = []

    def place_mug_in_reachable_pose(self):
        # print("DEBUG: Placing mug on top of the BOX (as requested)...")
        
        try:
            # Get box details
            box_pos = self.box.get_position()
            min_x, max_x, min_y, max_y, min_z, max_z = self.box.get_bounding_box()
            
            # Calculate top of the box
            # Bounding box is usually local. If box is at Z, top is Z + max_z
            box_top_z = box_pos[2] + max_z
            # print(f"DEBUG: Box found at {box_pos}, Top Z estimated at {box_top_z:.3f}")
            
            # Define a search grid ON THE BOX
            # We'll search a small area on top of the box
            # Assuming box is roughly centered at box_pos
            # We'll try a few spots relative to box center
            x_offsets = [0.0, 0.05, -0.05]
            y_offsets = [0.0, 0.05, -0.05]
            
            # Mug needs to be placed ON the box, so Z = box_top_z + mug_half_height?
            # Usually origin of mug is at bottom or center. 
            # If center, we need to add half height. If bottom, just box_top_z.
            # Let's assume origin is at bottom for now, or add a small safety margin.
            place_z = box_top_z + 0.005 
            
            grasp_quat = [1.0, 0.0, 0.0, 0.0] # Vertical grasp
            
            for x_off in x_offsets:
                for y_off in y_offsets:
                    test_pos = [box_pos[0] + x_off, box_pos[1] + y_off, place_z]
                    
                    # print(f"DEBUG: Checking reachability at {test_pos}...")
                    
                    # Check IK
                    path = self.robot.solve_ik_via_sampling(test_pos, quaternion=grasp_quat, max_configs=1, max_time_ms=50, ignore_collisions=True)
                    
                    if path is not None and len(path) > 0:
                        # print(f"DEBUG: SUCCESS - Found reachable pose on BOX at {test_pos}")
                        self.mug_box.set_position(test_pos)
                        return

            print("DEBUG: WARNING - Could not find reachable pose on box via IK check. Placing at center anyway.")
            self.mug_box.set_position([box_pos[0], box_pos[1], place_z])
            
        except Exception as e:
            print(f"DEBUG: Error placing mug on box: {e}")
            # Fallback
            r_pos = self.robot.get_position()
            self.mug_box.set_position([r_pos[0] + 0.5, r_pos[1], 0.9])

    def _get_path(self, q_start, target_pos, target_quat, target_conf=None, trials=20, max_time_ms=2000.0):
        # Helper to plan path using RRTConnect
        self.set_robot_conf(q_start)
        try:
            if target_pos is not None:
                # Plan to Cartesian target
                path = self.robot.get_path(position=target_pos, quaternion=target_quat,
                                           ignore_collisions=False,
                                           algorithm=ConfigurationPathAlgorithms.RRTConnect,
                                           max_configs=5, trials=trials, max_time_ms=max_time_ms)
            else:
                # Plan to Joint target
                # PyRep Panda.get_path expects a list of joint values if planning to config
                # and also needs ignore_collisions=False
                path = self.robot.get_path(config=list(target_conf),
                                           ignore_collisions=False,
                                           algorithm=ConfigurationPathAlgorithms.RRTConnect,
                                           max_configs=5, trials=trials, max_time_ms=max_time_ms)
            return path
        except Exception as e:
            print(f"DEBUG [Env]: Planning failed in _get_path: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_object(self, name):
        name = normalize_region_name(name)
        if name in self.name_to_obj:
            return self.name_to_obj[name]
        try:
            # Dynamic lookup
            obj = Shape(name)
            self.name_to_obj[name] = obj
            return obj
        except Exception:
            return None

    def get_robot_conf(self):
        return self.robot.get_joint_positions()

    def get_home_conf(self):
        """Return the stored home configuration captured at startup."""
        return list(self.home_conf)

    def save_conf(self, name, q=None):
        """Save a joint configuration under a given name."""
        import numpy as _np
        import os as _os
        if q is None:
            q = self.get_robot_conf()
        path = _os.path.join(self.state_dir, f"{name}.npy")
        _np.save(path, _np.array(q, dtype=_np.float32))

    def load_conf(self, name):
        """Load a previously saved joint configuration."""
        import numpy as _np
        import os as _os
        path = _os.path.join(self.state_dir, f"{name}.npy")
        if not _os.path.exists(path):
            raise FileNotFoundError(f"Saved conf '{name}' not found at {path}")
        return _np.load(path).tolist()

    def draw_trajectory(self, points, color=(1.0, 0.0, 0.0), size=4.0):
        """Draw a persistent 3D line strip trajectory in the scene.

        points: list of [x, y, z] world coordinates along the path.
        color:  RGB tuple in [0,1].
        size:   line width in pixels.
        """
        if not points:
            return

        options = sim.sim_drawing_lines | sim.sim_drawing_cyclic
        max_items = len(points)
        drawing_handle = sim.simAddDrawingObject(
            options,
            size,
            0.0,
            -1,
            max_items,
            [float(color[0]), float(color[1]), float(color[2])],
        )

        for p in points:
            coords = [float(p[0]), float(p[1]), float(p[2])]
            sim.simAddDrawingObjectItem(drawing_handle, coords)

    def set_robot_conf(self, q):
        self.robot.set_joint_positions(q)
        try:
            self.robot.set_joint_target_positions(q)
        except Exception:
            pass

    def _get_world_bounding_box(self, obj):
        """Get the axis-aligned bounding box of an object in world coordinates."""
        try:
            min_x, max_x, min_y, max_y, min_z, max_z = obj.get_bounding_box()
        except Exception:
            # Fallback for Dummy objects (reference points without volume)
            p = obj.get_position()
            # Return a tiny axis-aligned cube around the dummy position
            return p[0]-0.001, p[0]+0.001, p[1]-0.001, p[1]+0.001, p[2]-0.001, p[2]+0.001
        corners = np.array([
            [min_x, min_y, min_z], [min_x, min_y, max_z],
            [min_x, max_y, min_z], [min_x, max_y, max_z],
            [max_x, min_y, min_z], [max_x, min_y, max_z],
            [max_x, max_y, min_z], [max_x, max_y, max_z]
        ])
        
        # Transform to world
        matrix = obj.get_matrix()
        m = np.array(matrix)
        if m.size == 16:
            m = m.reshape(4, 4)
        elif m.size == 12:
            m = m.reshape(3, 4)
        
        world_corners = []
        for c in corners:
            # Homogeneous coordinate for corner
            c_h = np.append(c, 1.0)
            if m.shape == (4, 4):
                wc = np.dot(m, c_h)[:3]
            else:
                # 3x4 matrix
                wc = np.dot(m, c_h)
            world_corners.append(wc)
        world_corners = np.array(world_corners)
        
        w_min = np.min(world_corners, axis=0)
        w_max = np.max(world_corners, axis=0)
        return w_min[0], w_max[0], w_min[1], w_max[1], w_min[2], w_max[2]

    # -- cupboard placement (Phase 7c) -------------------------------------------------------
    CUPBOARD_WALL_THICKNESS = 0.011     # side/back walls and shelves of the cupboard model
    CUPBOARD_WALL_CLEARANCE = 0.02      # fingers beside the object + margin, from each side wall
    CUPBOARD_FRONT_INSET = 0.02         # an object's front face this far inside the open front
    # Widest horizontal side for the thin-side cupboard placement. This only chooses how the hand
    # is rolled at the cupboard; it never makes a pick possible that was not (the top-down pick is
    # planned as before). With the fingers closing along Y the object takes the side they closed
    # across, never more than with the previous roll (e.g. a sugar box knocked flat: 9 cm, not 18 cm).
    CUPBOARD_MAX_THIN = 0.10

    def cupboard_interior(self):
        """Usable interior of the lower cupboard shelf from the cupboard model: the open front,
        the back wall, the side walls' inner faces and the shelf top (all kitchen variants
        share the cupboard). Falls back to the cupboard_boundary strip without the model."""
        cup = getattr(self, 'cupboard', None)
        wall = float(os.environ.get('CUPBOARD_WALL_THICKNESS', str(self.CUPBOARD_WALL_THICKNESS)))
        if cup is not None:
            x0, x1, y0, y1, z0, _ = self._get_world_bounding_box(cup)
            return {'front_x': x0, 'back_x': x1 - wall, 'min_y': y0 + wall, 'max_y': y1 - wall, 'shelf_z': z0 + wall}
        x0, x1, y0, y1, z0, z1 = self._get_world_bounding_box(self.cupboard_boundary)
        return {'front_x': x0, 'back_x': x1, 'min_y': y0, 'max_y': y1, 'shelf_z': z1 - 0.07}

    def cupboard_placement_spec(self, obj):
        """How a cupboard-bound object is picked and placed (None: previous behaviour).

        The object is picked top-down with the fingers closing across its thinner horizontal
        side (``closing_yaw``). At the cupboard the hand is horizontal (approach +X) and rolled so
        the fingers close horizontally along Y (``side_grasp_quat``): the object then lies with its
        vertical axis (as it rested on the table) along the cupboard's depth, its longer
        horizontal side vertical and its thinner horizontal side across the shelf, so it takes
        only ``thin`` of the shelf's width. The resting pose may be upright or lying on a side
        (whichever of the object's axes is nearest vertical; e.g. a sugar box that tipped over).
        Before Phase 7c the hand closed vertically at the cupboard, which laid the object's
        longer side across the shelf (sugar 9.5 cm instead of 3.5 cm). Requires the object to
        rest on a face (an axis within ~14 deg of vertical), a thinner horizontal side of at most
        ``CUPBOARD_MAX_THIN``, a longer side that fits under the upper shelf (20 cm), and a
        non-round footprint."""
        if os.environ.get('CUPBOARD_THIN_SIDE_PLACEMENT', '1') == '0':
            return None
        try:
            lx0, lx1, ly0, ly1, lz0, lz1 = obj.get_bounding_box()
            _, _, _, qx, qy, qz, qw = obj.get_pose()
        except Exception:
            return None
        R = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qw * qz), 2 * (qx * qz + qw * qy)],
            [2 * (qx * qy + qw * qz), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qw * qx)],
            [2 * (qx * qz - qw * qy), 2 * (qy * qz + qw * qx), 1 - 2 * (qx * qx + qy * qy)],
        ])
        dims = [lx1 - lx0, ly1 - ly0, lz1 - lz0]
        vertical = int(np.argmax(np.abs(R[2, :])))
        if abs(R[2, vertical]) < 0.97:
            return None                                  # not resting on a face
        a, b = [i for i in range(3) if i != vertical]
        thin, long = (a, b) if dims[a] <= dims[b] else (b, a)
        thin_side, long_side = float(dims[thin]), float(dims[long])
        if thin_side > self.CUPBOARD_MAX_THIN or long_side > 0.20 or long_side - thin_side < 0.01:
            return None                                  # too wide, too tall, or round/square
        closing_yaw = float(np.arctan2(R[1, thin], R[0, thin]))
        return {'long': long_side, 'thin': thin_side, 'height': float(dims[vertical]), 'closing_yaw': closing_yaw}

    def _placement_rng(self, obj, region_name):
        """Random generator for one placement sample (Phase 7c).

        With ``TAMP_TRIAL_SEED`` set (the trial runner sets it to the trial seed), the k-th sample
        for an (object, region) pair is drawn from a generator derived from (seed, object, region,
        k): the samples do not depend on how many random numbers other code (pddlstream's
        time-bounded sampling, the motion planner) consumed before. Without the variable the
        generator is unseeded."""
        import zlib
        try:
            name = str(obj.get_name())
        except Exception:
            name = str(obj)
        calls = self.__dict__.setdefault('_placement_calls', {})
        key = (name, str(region_name))
        calls[key] = calls.get(key, 0) + 1
        self._last_placement_call = calls[key]      # 1-based index of this sample for (object, region)
        seed = os.environ.get('TAMP_TRIAL_SEED', '').strip()
        if not seed:
            return np.random.default_rng()
        return np.random.default_rng([int(seed) % (2 ** 32), zlib.crc32(name.encode()), zlib.crc32(key[1].encode()),
                                      calls[key]])

    def _cupboard_free_candidates(self, obj, half_y, interior):
        """Shelf positions (y) where the object's width (half_y + margin) is clear of every
        other object on the shelf, ordered by how tightly they pack against an object or a
        side wall.

        Objects on the shelf form a row along y at its front (their depth does not matter:
        the shelf is 31 cm deep), so a spot is free when its y-interval is clear. Packing
        against a neighbour or a wall leaves the free width in one piece (Phase 7c: the old
        sampler picked among the 8 best spots of a coarse grid by centre distance and could
        target a spot overlapping a can).

        Spots come from the contiguous gaps between objects (and the side walls); the list
        interleaves the gaps (the tightest spot of each gap, then the next of each, ...), gaps in
        order of their tightest spot, so the planner's successive samples try every gap early
        instead of spending its sample budget in one gap whose spots are all unreachable.
        An object that sticks out past the open front (e.g. a spam box that settled leaning
        forward) blocks an extra ``CUPBOARD_PROTRUSION_MARGIN`` (2 cm) on each side: the hand
        passes it on the way in."""
        margin = float(os.environ.get('CUPBOARD_FREE_MARGIN', '0.01'))
        protrusion_margin = float(os.environ.get('CUPBOARD_PROTRUSION_MARGIN', '0.02'))
        clearance = float(os.environ.get('CUPBOARD_WALL_CLEARANCE', str(self.CUPBOARD_WALL_CLEARANCE)))
        min_y, max_y = interior['min_y'] + clearance, interior['max_y'] - clearance
        occupied = []
        seen = set()
        for name, other in getattr(self, 'name_to_obj', {}).items():
            if other is None or other == obj:
                continue
            if any(tag in str(name).lower() for tag in ('boundary', 'table', 'cupboard', 'box_base')):
                continue
            try:
                handle = int(other.get_handle())
            except Exception:
                handle = id(other)
            if handle in seen:
                continue
            seen.add(handle)
            try:
                bx0, bx1, by0, by1, bz0, bz1 = self._get_world_bounding_box(other)
            except Exception:
                continue
            if bz0 > interior['shelf_z'] + 0.25 or bz1 < interior['shelf_z'] - 0.02:
                continue                           # not on this shelf
            if bx1 < interior['front_x'] - 0.02 or bx0 > interior['back_x'] or by1 < min_y - 0.10 or by0 > max_y + 0.10:
                continue
            extra = protrusion_margin if bx0 < interior['front_x'] - 0.005 else 0.0   # sticks out of the front
            occupied.append((by0 - extra, by1 + extra))
        grid_y = max(2, int(os.environ.get('CUPBOARD_SAMPLE_GRID_Y', '41')))
        lo_y, hi_y = min_y + half_y + margin, max_y - half_y - margin
        if lo_y > hi_y:
            return []
        free = []
        for y in np.linspace(lo_y, hi_y, grid_y):
            y0, y1 = y - half_y - margin, y + half_y + margin
            if any(y0 < b1 and b0 < y1 for b0, b1 in occupied):
                continue
            edges_below = [b1 for b0, b1 in occupied if b1 <= y0] + [min_y]
            edges_above = [b0 for b0, b1 in occupied if b0 >= y1] + [max_y]
            gap = min(y0 - max(edges_below), min(edges_above) - y1)
            gap_id = round(max(edges_below), 4)            # the free interval this spot is in
            free.append((round(max(0.0, gap), 4), float(y), gap_id))
        # Tightest first within each gap; gaps ordered by their tightest spot (ties from the
        # low-y wall); then interleaved across gaps.
        by_gap = {}
        for gap, y, gap_id in sorted(free):
            by_gap.setdefault(gap_id, []).append((gap, y))
        gaps = sorted(by_gap.values(), key=lambda spots: (spots[0][0], spots[0][1]))
        if os.environ.get('CUPBOARD_DEBUG'):
            print(f'[Cupboard] {obj.get_name()} half_y={half_y:.4f} walls=({min_y:.3f}, {max_y:.3f}) '
                  f'occupied={[(round(a, 3), round(b, 3)) for a, b in sorted(occupied)]} '
                  f'gaps={[(round(spots[0][1], 3), len(spots)) for spots in gaps]}')
        ordered = []
        for rank in range(max((len(spots) for spots in gaps), default=0)):
            ordered.extend(spots[rank] for spots in gaps if rank < len(spots))
        return ordered

    def sample_stable_pose(self, obj, region_name):
        """Return a stable 7D pose (x,y,z,qx,qy,qz,qw) for obj in region."""
        rng = self._placement_rng(obj, region_name)
        region_name = normalize_region_name(region_name)
        region = self.regions.get(region_name)
        if not region:
            print(f"Region {region_name} not found, returning current pose")
            return obj.get_pose()

        # Use robust world bounding box calculation
        w_min_x, w_max_x, w_min_y, w_max_y, w_min_z, w_max_z = self._get_world_bounding_box(region)
        
        # Sample x and y within world bounds (with padding)
        padding = 0.05
        if region_name == "inside_box":
            padding = 0.12  # 12cm padding for inside_box to prevent wall collisions
            
        # Ensure padding doesn't invert the range
        if (w_max_x - w_min_x) < 2*padding: padding = (w_max_x - w_min_x) / 3.0
        if (w_max_y - w_min_y) < 2*padding: padding = (w_max_y - w_min_y) / 3.0
        
        current_pose = obj.get_pose()
        try:
            is_mug = "mug" in str(obj.get_name()).lower()
        except Exception:
            is_mug = False

        def sample_clear_xy(min_x, max_x, min_y, max_y, grid_n, occ_pad_xy, occ_pad_z, mode="best", exclude=(),
                            keep=None, strict_exclude=False):
            xs = np.linspace(min_x, max_x, grid_n).tolist()
            ys = np.linspace(min_y, max_y, grid_n).tolist()
            candidates = [(float(x), float(y)) for x in xs for y in ys]
            if exclude or keep:
                outside = [c for c in candidates
                           if not any(r[0] <= c[0] <= r[2] and r[1] <= c[1] <= r[3] for r in exclude)]
                kept = [c for c in outside if keep is None or keep(c)]
                # strict_exclude: relax the reach preference before ever sampling inside an
                # excluded region (a table placement must not land in another region).
                candidates = kept or (outside if strict_exclude and outside else candidates)

            occupied_xy = []
            seen_handles = set()
            occupancy_sources = []

            # Primary source: named scene objects registered in this env.
            for name, other in getattr(self, "name_to_obj", {}).items():
                if other is None or other == obj:
                    continue
                lname = str(name).lower()
                # Skip fixtures/boundaries; keep movable task objects only.
                if any(tag in lname for tag in ("boundary", "table", "cupboard", "box_base")):
                    continue
                try:
                    h = int(other.get_handle())
                except Exception:
                    h = None
                if (h is not None) and (h in seen_handles):
                    continue
                if h is not None:
                    seen_handles.add(h)
                occupancy_sources.append(other)

            # Fallback: known object attributes if name_to_obj map is sparse.
            if not occupancy_sources:
                for other in (
                    getattr(self, "mug_table", None),
                    getattr(self, "mug_box", None),
                    getattr(self, "mug_cupboard", None),
                    getattr(self, "mug_inside_box", None),
                    getattr(self, "can", None),
                    getattr(self, "bottle", None),
                    getattr(self, "tin", None),
                    getattr(self, "food_box", None),
                    getattr(self, "cereal", None),
                ):
                    if other is None or other == obj:
                        continue
                    occupancy_sources.append(other)

            for other in occupancy_sources:
                try:
                    ox, oy, oz = other.get_position()
                except Exception:
                    continue
                if (
                    (w_min_x - occ_pad_xy) <= ox <= (w_max_x + occ_pad_xy)
                    and (w_min_y - occ_pad_xy) <= oy <= (w_max_y + occ_pad_xy)
                    and (w_min_z - occ_pad_z) <= oz <= (w_max_z + occ_pad_z)
                ):
                    occupied_xy.append(np.array([ox, oy], dtype=float))

            if occupied_xy or exclude:
                occupied_xy = occupied_xy or [np.array([1e3, 1e3])]
                # Pick the candidate with maximum clearance to occupied objects.
                def _clearance_score(xy):
                    p = np.array([xy[0], xy[1]], dtype=float)
                    return min(float(np.linalg.norm(p - q)) for q in occupied_xy)

                # Shuffle to avoid deterministic tie bias in symmetric scenes.
                rng.shuffle(candidates)
                if mode == "clear_random":
                    # Any candidate with enough clearance, uniformly: the planner's repeated
                    # samples then cover the whole free area instead of the same few
                    # maximum-clearance spots (which can all be unreachable).
                    min_clear = float(os.environ.get("CLEAR_XY_MIN_CLEARANCE", "0.07"))
                    clear = [c for c in candidates if _clearance_score(c) >= min_clear]
                    if clear:
                        return clear[int(rng.integers(0, len(clear)))]
                    mode = "top_random"
                if mode == "top_random":
                    scored = sorted(candidates, key=_clearance_score, reverse=True)
                    top_n = max(1, min(len(scored), int(os.environ.get("CLEAR_XY_TOP_RANDOM", "8"))))
                    return scored[int(rng.integers(0, top_n))]
                return max(candidates, key=_clearance_score)

            return (
                float(rng.uniform(min_x, max_x)),
                float(rng.uniform(min_y, max_y)),
            )

        is_box_region = region_name in { BOX_STORAGE_REGION}
        if is_box_region:
            # Final variants: place only inside the box's placement area (x/y rectangle).
            area = (getattr(self, 'placement_areas', None) or {}).get(BOX_STORAGE_REGION)
            if area is not None:
                w_min_x, w_max_x = max(w_min_x, area[0]), min(w_max_x, area[2])
                w_min_y, w_max_y = max(w_min_y, area[1]), min(w_max_y, area[3])
            # In boxes, keep a small padding and bias to free XY to avoid unnecessary planner failures.
            box_padding = float(os.environ.get("BOX_REGION_SAMPLE_PADDING", "0.015"))
            # Keep the whole object footprint inside the box: pad by its half-extent
            # (a mug with its handle is ~10 cm long) plus a margin. With only the fixed
            # padding, corner samples put mugs into the walls, where later placements
            # knocked them out of the box.
            try:
                o_min_x, o_max_x, o_min_y, o_max_y, _, _ = self._get_world_bounding_box(obj)
                half_extent = 0.5 * max(o_max_x - o_min_x, o_max_y - o_min_y)
                box_padding = max(
                    box_padding,
                    half_extent + float(os.environ.get("BOX_REGION_WALL_MARGIN", "0.01")),
                )
            except Exception:
                pass
            if (w_max_x - w_min_x) < 2 * box_padding:
                box_padding = max(0.0, 0.1 * (w_max_x - w_min_x))
            if (w_max_y - w_min_y) < 2 * box_padding:
                box_padding = max(0.0, 0.1 * (w_max_y - w_min_y))

            min_x = w_min_x + box_padding
            max_x = w_max_x - box_padding
            min_y = w_min_y + box_padding
            max_y = w_max_y - box_padding
            if min_x > max_x:
                mid_x = 0.5 * (w_min_x + w_max_x)
                min_x = max_x = mid_x
            if min_y > max_y:
                mid_y = 0.5 * (w_min_y + w_max_y)
                min_y = max_y = mid_y

            sample_x, sample_y = sample_clear_xy(
                min_x,
                max_x,
                min_y,
                max_y,
                max(3, int(os.environ.get("BOX_REGION_SAMPLE_GRID", "4"))),
                float(os.environ.get("BOX_REGION_OCCUPANCY_PAD_XY", "0.03")),
                float(os.environ.get("BOX_REGION_OCCUPANCY_PAD_Z", "0.08")),
            )

            sample_z = w_min_z + float(os.environ.get("BOX_REGION_SAMPLE_Z_OFFSET", "0.012"))
            if is_mug:
                sample_z = max(sample_z, MUG_PLACEMENT_MIN_SAMPLE_Z)
        # region_name is normalized above (placement_boundary -> table_staging_area,
        # cupboard_lower -> cupboard_shelf); the old comparisons never matched, so these
        # placements ignored occupied spots.
        elif region_name in ('placement_boundary', 'table_staging_area'):
            placement_padding = float(os.environ.get("PLACEMENT_BOUNDARY_SAMPLE_PADDING", str(padding)))
            if (w_max_x - w_min_x) < 2 * placement_padding:
                placement_padding = 0
            if (w_max_y - w_min_y) < 2 * placement_padding:
                placement_padding = 0
            min_x = w_min_x + placement_padding
            max_x = w_max_x - placement_padding
            min_y = w_min_y + placement_padding
            max_y = w_max_y - placement_padding
            sample_x, sample_y = sample_clear_xy(
                min_x,
                max_x,
                min_y,
                max_y,
                max(3, int(os.environ.get("PLACEMENT_BOUNDARY_SAMPLE_GRID", "4"))),
                float(os.environ.get("PLACEMENT_BOUNDARY_OCCUPANCY_PAD_XY", "0.04")),
                float(os.environ.get("PLACEMENT_BOUNDARY_OCCUPANCY_PAD_Z", "0.12")),
            )

            # For placement boundary, we want to be on the table surface.
            table = self.regions.get('table')
            if table:
                _, _, _, _, _, t_max_z = self._get_world_bounding_box(table)
                sample_z = t_max_z + 0.005
            else:
                sample_z = w_min_z + 0.005
            if is_mug:
                sample_z = max(sample_z, MUG_PLACEMENT_MIN_SAMPLE_Z)
        elif region_name in ('cupboard_lower', 'cupboard_shelf'):
            # Phase 7c: the whole lower-shelf interior (side walls, open front) for every kitchen
            # variant, and only spots where the object's width is clear of every other object.
            # A side-graspable object stands upright with its long side along the depth; any
            # other object keeps the previous behaviour (turned by the horizontal insertion).
            interior = self.cupboard_interior()
            spec = self.cupboard_placement_spec(obj)
            if spec is not None:
                # The hand's tip is on the object's axis: the object lies with its longer footprint
                # side vertical, so its bottom is 1 cm above the shelf when the tip is at
                # shelf + long/2 + 1 cm; its top (facing the robot) is about 6 cm in front of the tip.
                half_x, half_y = 0.06, 0.5 * spec['thin']
                sample_z = interior['shelf_z'] + 0.5 * spec['long'] + 0.01
            else:
                try:
                    ox0, ox1, oy0, oy1, _, _ = self._get_world_bounding_box(obj)
                    half_x, half_y = 0.5 * max(ox1 - ox0, oy1 - oy0), 0.5 * max(ox1 - ox0, oy1 - oy0)
                except Exception:
                    half_x = half_y = 0.05
                sample_z = w_max_z + 0.005
            free = self._cupboard_free_candidates(obj, half_y, interior)
            if not free:
                raise NoFreePlacement(f'no free spot for {obj.get_name()} on the cupboard shelf')
            # The k-th sample for this object takes the k-th tightest free spot: the first reachable
            # one packs against a neighbour or a wall; the planner's retries (unreachable spots)
            # walk on through the free width.
            k = int(getattr(self, '_last_placement_call', 1)) - 1
            _, sample_y = free[k % len(free)]
            inset = float(os.environ.get('CUPBOARD_FRONT_INSET', str(self.CUPBOARD_FRONT_INSET)))
            sample_x = min(interior['front_x'] + inset + half_x, interior['back_x'] - half_x)
        elif region_name == 'table':
            # Anywhere on the table except inside another region: the box (whose floor
            # is at table height), the open box lid, the cupboard, and the placement areas.
            # The transfer check tests 'table' against position + local bounding box
            # (x -0.075..0.675 in the kitchen scenes); the table mesh itself is larger.
            try:
                t_min_x, t_max_x, t_min_y, t_max_y, _, _ = region.get_bounding_box()
                t_x, t_y, _ = region.get_position()
                w_min_x, w_max_x = max(w_min_x, t_x + t_min_x), min(w_max_x, t_x + t_max_x)
                w_min_y, w_max_y = max(w_min_y, t_y + t_min_y), min(w_max_y, t_y + t_max_y)
            except Exception:
                pass
            # Margins match the region resolver (llm_pipeline/region_geometry.py REGION_PADDING)
            # plus 3 cm (a placed object ends up to ~2 cm from the sampled point: grasp offset),
            # so a table placement is never observed in another region: regions at table height
            # (the box interior, the pantry and staging areas) get their padding plus that;
            # physical fixtures (box walls, the lid, the cupboard) get 2 cm of clearance.
            exclude = []
            for other, margin in ((getattr(self, 'box_boundary', None), 0.05), (getattr(self, 'box', None), 0.02),
                                  (getattr(self, 'box_lid', None), 0.02),
                                  (getattr(self, 'cupboard_boundary', None), 0.02),
                                  (getattr(self, 'cupboard', None), 0.02),
                                  (getattr(self, 'groceries_boundary', None), 0.03),
                                  (getattr(self, 'placement_boundary', None), 0.03)):
                if other is None:
                    continue
                try:
                    bx0, bx1, by0, by1, _, _ = self._get_world_bounding_box(other)
                except Exception:
                    continue
                exclude.append((bx0 - margin, by0 - margin, bx1 + margin, by1 + margin))
            for area in (getattr(self, 'placement_areas', None) or {}).values():
                exclude.append((area[0] - 0.05, area[1] - 0.05, area[2] + 0.05, area[3] + 0.05))
            # Within the arm's comfortable reach: a ring around the robot base.
            try:
                rx, ry, _ = self.robot.get_position()
            except Exception:
                rx, ry = None, None
            reach = None
            if rx is not None:
                # 0.28 m includes the free patch in front of the robot, between the pantry and
                # staging areas (the only table surface outside every region that is reachable
                # without passing over staged objects).
                reach_min, reach_max = 0.28, 0.62
                reach = lambda c: reach_min <= float(np.hypot(c[0] - rx, c[1] - ry)) <= reach_max  # noqa: E731
            sample_x, sample_y = sample_clear_xy(
                w_min_x + padding, w_max_x - padding, w_min_y + padding, w_max_y - padding,
                max(3, int(os.environ.get("TABLE_SAMPLE_GRID", "48"))),
                float(os.environ.get("TABLE_OCCUPANCY_PAD_XY", "0.04")),
                float(os.environ.get("TABLE_OCCUPANCY_PAD_Z", "0.12")),
                mode="clear_random", exclude=exclude, keep=reach, strict_exclude=True,
            )
            sample_z = w_max_z + 0.005
        else:
            sample_x = rng.uniform(w_min_x + padding, w_max_x - padding)
            sample_y = rng.uniform(w_min_y + padding, w_max_y - padding)

            # Default (Table)
            sample_z = w_max_z + 0.005
            
        # Use the sampled x,y and guessed z
        new_pose = list(current_pose)
        new_pose[0] = sample_x
        new_pose[1] = sample_y
        new_pose[2] = sample_z 
        
        return new_pose


    def _get_linear_path(self, q_start, target_pos, target_quat, ignore_collisions=False, steps=50):
        self.set_robot_conf(q_start)
        try:
            # steps=50 for finer resolution
            path = self.robot.get_linear_path(position=target_pos, quaternion=target_quat, steps=steps, ignore_collisions=ignore_collisions)
            return path
        except Exception as e:
            # print(f"Linear path failed: {e}")
            return None

    def _interpolate_joint_path(self, q1, q2, steps=50, check_collisions=True):
        """Generate a simple joint-space interpolation, optionally collision-checked."""
        traj = []
        q1 = np.array(q1)
        q2 = np.array(q2)
        
        # Use high resolution for safety
        if steps < 50: steps = 50

        for i in range(steps + 1):
            t = i / steps
            q = (1 - t) * q1 + t * q2
            q_list = q.tolist()

            if check_collisions:
                self.set_robot_conf(q_list)
                if self.robot.check_collision():
                    return None

            traj.append(q_list)
        return traj

    def compute_retreat_to_home(self, q_start):
        """Plan a retreat from the current config back to the stored home pose."""
        q_home = list(self.home_conf)
        
        # 1. Try simple interpolation first (fastest)
        traj = self._interpolate_joint_path(q_start, q_home, steps=50, check_collisions=True) # Increased to 50
        if traj:
            return q_home, traj
            
        # 2. If blocked, use RRTConnect
        # print("DEBUG: Retreat interpolation blocked, trying RRT...")
        self.set_robot_conf(q_start)
        try:
            path = self.robot.get_path(position=None, quaternion=None,
                                     ignore_collisions=False,
                                     algorithm=ConfigurationPathAlgorithms.RRTConnect,
                                     max_configs=5, trials=20, max_time_ms=1000.0)
            # We need to set the target to home configuration, but get_path usually takes cartesian.
            # PyRep's get_path is for Cartesian. For joint space, we need get_linear_path (which is linear) 
            # or we need to use OMPL for joint space.
            # Actually, PyRep's get_path is Cartesian. 
            # Let's use a simple trick: Move to a high "safe" intermediate point if direct fails?
            # Or just rely on the fact that "Home" is usually safe.
            
            # If direct interpolation fails, it's likely we are deep in a bin.
            # Let's try to lift up first (Z+), then go home.
            
            # Get current cartesian pose
            curr_pos = self.robot.get_position()
            curr_quat = self.robot.get_quaternion()
            
            # Lift by 20cm
            lift_pos = [curr_pos[0], curr_pos[1], curr_pos[2] + 0.2]
            path_lift = self.robot.get_linear_path(position=lift_pos, quaternion=curr_quat, steps=30, ignore_collisions=False) # Increased to 30
            
            if path_lift:
                # From lift end, go home
                q_lift_end = path_lift._path_points[-7:].tolist()
                traj_home = self._interpolate_joint_path(q_lift_end, q_home, steps=50, check_collisions=True) # Increased to 50
                if traj_home:
                    # Combine
                    traj_lift = path_lift._path_points.reshape(-1, 7).tolist()
                    # FORCE CONTINUITY: Ensure the path starts exactly at q_start
                    traj_lift[0] = list(q_start)
                    return q_home, traj_lift + traj_home
            
            return None, None
        except Exception:
            return None, None

    def compute_motion_plan(self, q1, q2):
        """Plan a path from q1 to q2 with collision checking."""
        try:
            # Special case: retreat back to the startup configuration.
            if np.allclose(q2, self.home_conf, atol=1e-3):
                _, traj = self.compute_retreat_to_home(q1)
                return traj

            # Calculate FK for q1 (Start)
            self.set_robot_conf(q1)
            p1 = self.robot.get_position()
            quat1 = self.robot.get_quaternion()

            # Check holding status
            grasped_objects = self.gripper.get_grasped_objects()
            is_holding = (len(grasped_objects) > 0)

            # Check if we are "in the box" (or close to it)
            # If so, we MUST lift first to avoid rim collision during interpolation dip.
            in_box = False
            if getattr(self, 'box', None) is not None:
                box_pos = np.array(self.box.get_position())
                min_x, max_x, min_y, max_y, min_z, max_z = self.box.get_bounding_box()
                # World bounds with margin
                bx_min = box_pos[0] + min_x - 0.05
                bx_max = box_pos[0] + max_x + 0.05
                by_min = box_pos[1] + min_y - 0.05
                by_max = box_pos[1] + max_y + 0.05
                bz_max = box_pos[2] + max_z + 0.10 # Reduced safety height threshold (was 0.20)

                if (bx_min < p1[0] < bx_max) and (by_min < p1[1] < by_max) and (p1[2] < bz_max):
                    in_box = True
                    # print("DEBUG: Start position is inside/near box. Forcing Lift maneuver.")

            if not in_box and not is_holding:
                # Increased steps to 50 for smoothness
                traj = self._interpolate_joint_path(q1, q2, steps=50, check_collisions=True)
                if traj:
                    print(f"DEBUG [Env]: Interpolation success for q1->q2")
                    return traj
                else:
                    print(f"DEBUG [Env]: Interpolation failed (collision), trying safe lift/retreat maneuver.")
                
            # 2. SAFETY MANEUVER: If direct path fails (collision) OR we are in box OR holding, try to Lift/Retract first.
            # This fixes the "hitting cupboard" issue by forcing a crane-like move.
            
            # (p1 and quat1 are already calculated above)
            
            # Try to lift up significantly (0.25m) to clear obstacles (e.g. open lid)
            p_lift = [p1[0], p1[1], p1[2] + 0.25] # Increased from 0.15 for safety
            
            # Plan q1 -> q_lift
            path_lift = self.robot.get_linear_path(position=p_lift, quaternion=quat1, steps=30, ignore_collisions=False) # Increased to 30
            
            if path_lift:
                q_lift = path_lift._path_points[-7:].tolist()
                traj_lift = path_lift._path_points.reshape(-1, 7).tolist()
                # FORCE CONTINUITY: Ensure the path starts exactly at q1
                traj_lift[0] = list(q1)
                
                # Now try q_lift -> q2
                # We use RRTConnect here because q_lift -> q2 might be complex
                # We need joint path. Let's use RRT here.
                path_rest = self._get_path(q_lift, None, None, target_conf=q2)
                if path_rest:
                    traj_rest = path_rest._path_points.reshape(-1, 7).tolist()
                    return traj_lift + traj_rest
                
                # If RRT fails, try interpolate as final fallback
                traj_rest_interp = self._interpolate_joint_path(q_lift, q2, steps=100, check_collisions=True)
                
                if traj_rest:
                    return traj_lift + traj_rest
                
                # If interpolation fails, try via Home (High -> Home -> Target)
                if not np.allclose(q_lift, self.home_conf, atol=1e-3):
                    traj_home = self._interpolate_joint_path(q_lift, self.home_conf, steps=50, check_collisions=True) # Increased to 50
                    if traj_home:
                        traj_final = self._interpolate_joint_path(self.home_conf, q2, steps=100, check_collisions=True) # Increased to 100
                        if traj_final:
                            return traj_lift + traj_home + traj_final

            # 3. If that fails, try moving via Home configuration directly
            if not np.allclose(q1, self.home_conf, atol=1e-3):
                # Plan q1 -> Home
                _, traj_to_home = self.compute_retreat_to_home(q1)
                if traj_to_home:
                    # Plan Home -> q2
                    traj_from_home = self._interpolate_joint_path(self.home_conf, q2, steps=100, check_collisions=True) # Increased to 100
                    if traj_from_home:
                        return traj_to_home + traj_from_home

            # 4. If that fails, return None (Planner will retry or fail)
            # print(f"DEBUG: Motion plan failed for q1->q2 (Collision)")
            return None
        except Exception as e:
            # print(f"DEBUG: compute_motion_plan failed for q1={q1} q2={q2}: {e}")
            return None

    def set_target_region(self, name):
        self.target_region_name = normalize_region_name(name)

    def compute_pick_trajectory(self, obj, pose):
        """Return grasp, q_start, q_end, and trajectory for picking obj at pose."""
        print(f"DEBUG [Env]: Starting compute_pick_trajectory for {obj.get_name()}")
        original_conf = self.get_robot_conf()
        pick_timeout_s = float(os.environ.get("PICK_TRAJECTORY_TIMEOUT_S", "8.0"))
        started_at = time.monotonic()

        def _check_pick_timeout():
            if (time.monotonic() - started_at) > pick_timeout_s:
                raise RuntimeError(
                    f"Pick planning timed out while computing trajectory for {obj.get_name()} after {pick_timeout_s:.1f}s"
                )
        
        # Handle obstructions for specific objects
        # ONLY disable lid collision if lid is actually OPEN (slid away)
        # Otherwise, let IK fail so COAST can learn the constraint
        lid_obj = None
        lid_collidable_state = True
        if obj.get_name() == 'mug4': # mug_inside_box is mug4
             lid_obj = self.get_object('box_lid')
             if lid_obj:
                 # Check if lid is actually open by checking its position
                 # Lid slides in X direction when opened (see compute_slide_lid_trajectory)
                 lid_pos = lid_obj.get_position()
                 box_obj = self.get_object('box_base')
                 if box_obj:
                     box_pos = box_obj.get_position()
                     # If lid has moved significantly in X, it's open
                     lid_offset = abs(lid_pos[0] - box_pos[0])
                     LID_OPEN_THRESHOLD = 0.10  # 10cm offset in X means open
                     print(f"DEBUG: Lid check - lid_pos={lid_pos}, box_pos={box_pos}, X_offset={lid_offset:.3f}")
                     if lid_offset > LID_OPEN_THRESHOLD:
                         # Lid is open, safe to disable collision for planning
                         lid_collidable_state = lid_obj.is_collidable()
                         lid_obj.set_collidable(False)
                         print(f"DEBUG: Lid is OPEN (X_offset={lid_offset:.3f}), disabling collision")
                     else:
                         # Lid is CLOSED - DO NOT disable collision
                         # Let IK fail naturally so COAST can learn
                         print(f"DEBUG: Lid is CLOSED (X_offset={lid_offset:.3f}), keeping collision ON - IK should fail!")
                         lid_obj = None  # Don't restore later since we didn't change it
                 
        try:
            # 1. Analyze object geometry.
            # Default path keeps legacy behavior. Adaptive path is enabled only
            # when object Z has drifted from planned pose (e.g., tipped/moved).
            min_x, max_x, min_y, max_y, min_z, max_z = obj.get_bounding_box()
            obj_height = max_z - min_z
            top_z_local = max_z
            live_pose = obj.get_pose()
            live_pos = obj.get_position()
            w_min_x, w_max_x, w_min_y, w_max_y, w_min_z, w_max_z = self._get_world_bounding_box(obj)
            obj_height_world = max(w_max_z - w_min_z, 0.02)
            planned_pose = list(pose) if pose is not None else list(live_pose)
            z_drift = abs(float(live_pos[2]) - float(planned_pose[2])) if len(planned_pose) >= 3 else 0.0

            # Also enable adaptive mode when the object is significantly tilted.
            # This is critical for mugs lying on table: local bbox "top" is not
            # aligned with world +Z, so legacy top grasp can miss entirely.
            tilted_object = False
            upright_score = 1.0
            if len(live_pose) >= 7:
                qx, qy, qz, qw = (
                    float(live_pose[3]),
                    float(live_pose[4]),
                    float(live_pose[5]),
                    float(live_pose[6]),
                )
                z_axis_world_z = 1.0 - 2.0 * (qx * qx + qy * qy)
                upright_score = abs(float(z_axis_world_z))
                tilted_object = upright_score < 0.75

            adaptive_pick_mode = (z_drift > 0.015) or tilted_object  # 1.5 cm / tilted threshold
            if adaptive_pick_mode:
                reason = f"z_drift={z_drift:.3f}m"
                if tilted_object:
                    reason += f", tilt_score={upright_score:.3f}"
                # Suppressed: only print in debug mode
                # print(f"DEBUG: Adaptive pick mode ON for {obj.get_name()} ({reason})")
            
            # Check if object is truly inside cupboard region.
            # IMPORTANT: do not infer cupboard status by object name (e.g., mug3 can be on table later).
            in_cupboard = False
            if getattr(self, 'cupboard_boundary', None) is not None:
                bb_min_x, bb_max_x, bb_min_y, bb_max_y, bb_min_z, bb_max_z = self._get_world_bounding_box(self.cupboard_boundary)
                ref_pos = live_pos if adaptive_pick_mode else planned_pose
                inside_cupboard_bbox = (
                    (bb_min_x <= ref_pos[0] <= bb_max_x)
                    and (bb_min_y <= ref_pos[1] <= bb_max_y)
                    and (bb_min_z <= ref_pos[2] <= bb_max_z)
                )
                if inside_cupboard_bbox:
                    # If object is near table height, treat it as table object and use vertical pick.
                    table_top_z = None
                    table_obj = getattr(self, 'table', None)
                    if table_obj is None:
                        table_obj = self.regions.get('table') if hasattr(self, 'regions') else None
                    if table_obj is not None:
                        _, _, _, _, _, table_top_z = self._get_world_bounding_box(table_obj)
                    if (table_top_z is not None) and (ref_pos[2] <= (table_top_z + 0.10)):
                        pass  # overlaps cupboard XY but near table height — vertical pick
                    else:
                        in_cupboard = True

            if in_cupboard:
                # --- HORIZONTAL PICK STRATEGY ---
                # Target Pose: Object's current position
                ref_pos = live_pos if adaptive_pick_mode else planned_pose
                cupboard_pick_height_offset = 0.05
                target_pos = [
                    ref_pos[0],
                    ref_pos[1],
                    ref_pos[2] + cupboard_pick_height_offset,
                ]
                
                # Hover Pose: In front of cupboard (shifted -X)
                # User requested 25cm clearance and strictly horizontal approach
                hover_dist = 0.25 
                hover_pos = [ref_pos[0] - hover_dist, ref_pos[1], target_pos[2]]
                
                # Grasp Orientation: Horizontal (Fingers Horizontal)
                # Base orientation: Ry=pi/2 (Z points +X)
                import math
                def quaternion_from_euler(ai, aj, ak):
                    ai /= 2.0
                    aj /= 2.0
                    ak /= 2.0
                    ci = math.cos(ai)
                    si = math.sin(ai)
                    cj = math.cos(aj)
                    sj = math.sin(aj)
                    ck = math.cos(ak)
                    sk = math.sin(ak)
                    cc = ci*ck
                    cs = ci*sk
                    sc = si*ck
                    ss = si*sk
                    q = [cj*sc - sj*cs, cj*ss + sj*cc, cj*cs - sj*sc, cj*cc + sj*ss]
                    return q

                base_ry = np.pi/2
                # Strictly Horizontal Fingers (Roll = 0 or 180)
                grasp_quats = [
                    quaternion_from_euler(0, base_ry, 0),       # Fingers Horizontal
                    quaternion_from_euler(np.pi, base_ry, 0),   # Fingers Horizontal (flipped)
                ]
                
                # --- NEW: Extensive Sampling (Shotgun Approach) ---
                # Sample a grid around the object center to find ANY valid IK solution.
                # Added small positive Z bias to avoid scraping the shelf
                z_offsets = [0.02, 0.04, 0.0, -0.02, 0.05] 
                y_offsets = [0.0, 0.02, -0.02, 0.04, -0.04]
                
                for z_off in z_offsets:
                    _check_pick_timeout()
                    for y_off in y_offsets:
                        _check_pick_timeout()
                        target_pos_sample = [target_pos[0], target_pos[1] + y_off, target_pos[2] + z_off]
                        hover_pos_sample = [hover_pos[0], hover_pos[1] + y_off, hover_pos[2] + z_off]
                        
                        for grasp_rot in grasp_quats:
                            _check_pick_timeout()
                            try:
                                # A. Solve IK for Hover Pose
                                path_configs_hover = self.robot.solve_ik_via_sampling(hover_pos_sample, quaternion=grasp_rot, max_configs=20, max_time_ms=500, ignore_collisions=True)
                                if path_configs_hover is None or len(path_configs_hover) == 0: 
                                    continue
                                
                                # Sort by distance to current config to find "natural" posture
                                curr_q = self.get_robot_conf()
                                path_configs_hover = sorted(path_configs_hover, key=lambda q: np.linalg.norm(np.array(q) - np.array(curr_q)))
                                q_hover = path_configs_hover[0]
                                
                                # B. Solve IK for Grasp Pose
                                path_configs_grasp = self.robot.solve_ik_via_sampling(target_pos_sample, quaternion=grasp_rot, max_configs=20, max_time_ms=500, ignore_collisions=True)
                                if path_configs_grasp is None or len(path_configs_grasp) == 0: 
                                    continue
                                
                                # Sort by distance to q_hover to ensure smooth transition
                                path_configs_grasp = sorted(path_configs_grasp, key=lambda q: np.linalg.norm(np.array(q) - np.array(q_hover)))
                                q_grasp = path_configs_grasp[0]
                                
                                # C. Plan Hover -> Grasp (Linear Approach)
                                # Force ignore_collisions=True to ensure we don't get blocked by minor grazes
                                path_approach = self._get_linear_path(q_hover, target_pos_sample, grasp_rot, steps=50, ignore_collisions=True)
                                if not path_approach: 
                                    continue
                                
                                # D. Plan Grasp -> Hover (Linear Retreat with Slant Lift)
                                # Lift 3cm during retreat to avoid friction
                                lifted_hover_pos = [hover_pos_sample[0], hover_pos_sample[1], hover_pos_sample[2] + 0.03]
                                path_retreat = self._get_linear_path(q_grasp, lifted_hover_pos, grasp_rot, steps=50, ignore_collisions=True)
                                if not path_retreat:
                                    path_approach.remove()
                                    continue
                                    
                                # Extract configs
                                def get_configs(p):
                                    return p._path_points.reshape(-1, 7).tolist()

                                t_approach = get_configs(path_approach)
                                t_retreat = get_configs(path_retreat)
                                
                                grasp = [0]*7
                                # pick found at cupboard offset Y={y_off}, Z={z_off}
                                # Return split trajectories
                                return grasp, q_hover, q_hover, (t_approach, t_retreat)

                            except Exception:
                                continue
                
                print("DEBUG: Horizontal pick failed for all orientations and offsets.")
                # Don't raise yet, let it fall through? No, fall through means vertical grasp which is bad.
                raise RuntimeError("Could not find valid horizontal pick configuration for cupboard")

            # ALWAYS USE TOP GRASP (Vertical) per user request
            # 2. Define Grasp Strategy (Top-Down Depth Sampling)
            grasp_depths = [0.02, 0.04, 0.06, 0.08]
            if adaptive_pick_mode:
                valid_depths = [d for d in grasp_depths if d < (obj_height_world - 0.005)]
            else:
                valid_depths = [d for d in grasp_depths if d < (obj_height - 0.01)]
            if not valid_depths:
                valid_depths = [obj_height_world / 2.0] if adaptive_pick_mode else [obj_height / 2.0]

            # 3. Define Grasp Orientations
            grasp_quats = []
            import math
            def quaternion_from_euler(ai, aj, ak):
                ai /= 2.0
                aj /= 2.0
                ak /= 2.0
                ci = math.cos(ai)
                si = math.sin(ai)
                cj = math.cos(aj)
                sj = math.sin(aj)
                ck = math.cos(ak)
                sk = math.sin(ak)
                cc = ci*ck
                cs = ci*sk
                sc = si*ck
                ss = si*sk
                q = [cj*sc - sj*cs, cj*ss + sj*cc, cj*cs - sj*sc, cj*cc + sj*ss]
                return q

            # Check if object is inside the executable box-inside region.
            in_box_region = False
            box_inside_region = self.regions.get(BOX_STORAGE_REGION)
            if box_inside_region is not None:
                o_pos = obj.get_position()
                bb_min_x, bb_max_x, bb_min_y, bb_max_y, bb_min_z, bb_max_z = self._get_world_bounding_box(box_inside_region)
                if (bb_min_x <= o_pos[0] <= bb_max_x) and (bb_min_y <= o_pos[1] <= bb_max_y) and (bb_min_z <= o_pos[2] <= bb_max_z):
                    in_box_region = True
                    # object detected inside box-inside, restricting grasp orientation

            if in_box_region:
                 # User request: aligned with x axis, no orientation/angle in xy axis
                 # We'll use 0, pi/2, pi, 3pi/2 to cover both alignments (fingers along X or Y)
                 angles = [0, np.pi/2, np.pi, 3*np.pi/2]
            else:
                 if adaptive_pick_mode:
                     # Bias around current yaw when object pose has drifted.
                     qx, qy, qz, qw = live_pose[3], live_pose[4], live_pose[5], live_pose[6]
                     obj_yaw = np.arctan2(2.0 * (qw * qz + qx * qy),
                                          1.0 - 2.0 * (qy * qy + qz * qz))
                     yaw_offsets = [0.0, np.pi/8, -np.pi/8, np.pi/4, -np.pi/4]
                     primary = [obj_yaw + d for d in yaw_offsets]
                     fallback = list(np.linspace(0, 2*np.pi, 16, endpoint=False))
                     angles = primary + fallback
                 else:
                     # Legacy behavior
                     angles = np.linspace(0, 2*np.pi, 16)

            cupboard_spec = (self.cupboard_placement_spec(obj)
                             if getattr(self, 'target_region_name', None) in CUPBOARD_TARGET_REGIONS else None)
            if cupboard_spec is not None:
                # Phase 7c: close exactly across the thin side (the fingers close along the grasp
                # frame's x axis = (cos angle, sin angle)), so the cupboard place (fingers along Y)
                # puts the thin side across the shelf.
                closing = cupboard_spec['closing_yaw']
                angles = [closing, closing + np.pi] + [closing + d for d in (np.pi / 12, -np.pi / 12)] + list(angles)
            for angle in angles:
                q = quaternion_from_euler(np.pi, 0, angle)
                grasp_quats.append(q)
            # An elongated object (e.g. a phone lying flat) wider than the gripper
            # opening in one direction: try first the grasps whose fingers close
            # across its shorter side (the fingers close along the grasp frame's x axis).
            ext_x, ext_y = (w_max_x - w_min_x), (w_max_y - w_min_y)
            if cupboard_spec is None and abs(ext_x - ext_y) > 0.01 and max(ext_x, ext_y) > 0.07:
                long_axis = np.array([1.0, 0.0, 0.0]) if ext_x > ext_y else np.array([0.0, 1.0, 0.0])

                def _closing_alignment(q):
                    x, y, z, w = q
                    closing = np.array([1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)])
                    return abs(float(np.dot(closing, long_axis)))

                grasp_quats.sort(key=_closing_alignment)
            
            # 4. Iterate and Solve
            if adaptive_pick_mode:
                # For tipped/fallen objects on table, try a few nearby XY grasp points
                # while preserving strict vertical approach/retreat.
                xy_offsets = [
                    (0.0, 0.0),
                    (0.01, 0.0), (-0.01, 0.0),
                    (0.0, 0.01), (0.0, -0.01),
                ]
            else:
                xy_offsets = [(0.0, 0.0)]

            for depth in valid_depths:
                _check_pick_timeout()
                if adaptive_pick_mode:
                    # Adaptive: derive grasp from live world top.
                    target_z = max(w_min_z + 0.005, w_max_z - depth)
                    base_x, base_y = live_pos[0], live_pos[1]
                else:
                    # Legacy: use planned pose and local bbox.
                    target_z = planned_pose[2] + top_z_local - depth
                    base_x, base_y = planned_pose[0], planned_pose[1]

                for dx, dy in xy_offsets:
                    _check_pick_timeout()
                    if in_box_region:
                        target_pos = [live_pos[0], live_pos[1], target_z]
                        hover_pos = [live_pos[0], live_pos[1], live_pos[2] + 0.15] # Changed from 0.40 to 0.15 to avoid kinematic limits
                    else:
                        target_pos = [base_x + dx, base_y + dy, target_z]
                        hover_pos = [target_pos[0], target_pos[1], target_pos[2] + 0.10] # Changed from 0.25 to 0.10
                    # Keep approach strictly vertical in Cartesian space.

                    for i, grasp_rot in enumerate(grasp_quats):
                        _check_pick_timeout()
                        try:
                            # A. Solve IK for Grasp Pose
                            path_configs = self.robot.solve_ik_via_sampling(
                                target_pos, quaternion=grasp_rot, max_configs=5, max_time_ms=50, ignore_collisions=True
                            )
                            if path_configs is None or len(path_configs) == 0:
                                continue
                            q_grasp = path_configs[0]

                            # B. Solve IK for Hover Pose
                            path_configs_hover = self.robot.solve_ik_via_sampling(
                                hover_pos, quaternion=grasp_rot, max_configs=5, max_time_ms=50, ignore_collisions=True
                            )
                            if path_configs_hover is None or len(path_configs_hover) == 0:
                                continue
                            q_hover = path_configs_hover[0]

                            # C. Plan Hover -> Grasp (linear vertical descent)
                            path2 = self._get_linear_path(q_hover, target_pos, grasp_rot, ignore_collisions=True)
                            if not path2:
                                continue

                            q_grasp_actual = path2._path_points[-7:].tolist()

                            # D. Plan Grasp -> Hover (linear vertical lift)
                            path3 = self._get_linear_path(q_grasp_actual, hover_pos, grasp_rot, ignore_collisions=True)
                            if not path3:
                                path2.remove()
                                continue

                            q_hover_end = path3._path_points[-7:].tolist()

                            def get_configs(p):
                                return p._path_points.reshape(-1, 7).tolist()

                            t2 = get_configs(path2)
                            t3 = get_configs(path3)

                            grasp = [0]*7
                            if not adaptive_pick_mode:
                                # Phase 7c: how far below the object's top the fingers hold it (the
                                # cupboard thin-side place sets its insertion depth from it).
                                self.__dict__.setdefault('planned_grasp_depths', {})[obj.get_name()] = float(depth)
                            return grasp, q_hover, q_hover_end, (t2, t3)

                        except Exception:
                            continue

            total_tried = len(valid_depths) * len(grasp_quats)
            print(f"DEBUG: compute_pick_trajectory failed for {obj} at {pose}. Tried {total_tried} configs.")
            raise RuntimeError(f"Could not find valid grasp configuration after {total_tried} attempts")
        finally:
            self.set_robot_conf(original_conf)
            # Restore lid collidability
            if lid_obj:
                lid_obj.set_collidable(lid_collidable_state)

    def compute_place_trajectory(self, obj, pose, region_name=None):
        """Return grasp, q_start, q_end, and trajectory for placing obj at pose (LOWER & RELEASE)."""
        original_conf = self.get_robot_conf()
        place_targets = None   # Phase 7c: several (place, hover) targets for the cupboard thin-side place
        try:
            # 1. Determine Strategy based on Region
            region_name = normalize_region_name(region_name)
            is_cupboard = region_name in CUPBOARD_TARGET_REGIONS
            is_box_region = region_name in {BOX_STORAGE_REGION}
            
            min_x, max_x, min_y, max_y, min_z, max_z = obj.get_bounding_box()
            top_z_local = max_z
            
            if is_cupboard:
                # --- HORIZONTAL APPROACH (Front) ---
                # User requirement: "hover at some distance in front o the cupboard.. and then perform the place, where it just goes ahead in the x direction"
                
                # Target Pose (Final Place)
                # Use the sampled pose directly to avoid IK failures and deep placement
                target_pos_place = [pose[0], pose[1], pose[2]]
                
                # Hover Pose (Start/End)
                # "hover at some distance in front"
                # We keep the hover pose back relative to the original pose to ensure clearance
                # User requested strict straight line (horizontal) for cupboard, so removing Z offset
                # Increased hover_dist to 0.40 to give more room for horizontal alignment
                hover_dist = 0.40
                target_pos_hover = [pose[0] - hover_dist, pose[1], pose[2]]
                
                import math
                def quaternion_from_euler(ai, aj, ak):
                    ai /= 2.0
                    aj /= 2.0
                    ak /= 2.0
                    ci = math.cos(ai)
                    si = math.sin(ai)
                    cj = math.cos(aj)
                    sj = math.sin(aj)
                    ck = math.cos(ak)
                    sk = math.sin(ak)
                    cc = ci*ck
                    cs = ci*sk
                    sc = si*ck
                    ss = si*sk
                    q = [cj*sc - sj*cs, cj*ss + sj*cc, cj*cs - sj*sc, cj*cc + sj*ss]
                    return q

                grasp_quats = []
                # Try multiple rolls to find one that works (e.g. fingers horizontal vs vertical)
                # Base orientation: Ry=pi/2 (Z points +X)
                base_ry = np.pi/2
                cupboard_spec = self.cupboard_placement_spec(obj)
                if cupboard_spec is not None:
                    # Phase 7c: fingers closing horizontally (along Y) at the cupboard, so the
                    # object's thin side (the one the top-down pick closed across) is across the
                    # shelf. Both roll signs give the same footprint. The hand in this roll only
                    # clears the shelf when the tip is well above it, so the tip goes only as deep
                    # as needed (the object's near face 1 cm inside the open front; the object
                    # itself reaches into the cupboard) and at the lowest collision-free height,
                    # from the object's bottom 1 cm above the shelf upwards.
                    grasp_quats.extend([side_grasp_quat(0.0, np.pi / 2), side_grasp_quat(0.0, -np.pi / 2)])
                    interior = self.cupboard_interior()
                    depth = float((getattr(self, 'planned_grasp_depths', {}) or {}).get(obj.get_name(), 0.02))
                    tip_x = interior['front_x'] + 0.01 + depth
                    lowest = interior['shelf_z'] + 0.5 * cupboard_spec['long'] + 0.01
                    place_targets = []
                    for dz in np.arange(0.0, 0.10, 0.01):
                        z = max(lowest, float(pose[2])) + dz
                        place_targets.append(([tip_x, pose[1], z], [tip_x - hover_dist, pose[1], z]))
                else:
                    # User requires strict "FACING X DIRECTION" without weird rotations.
                    # Restricting to roll=0 ensures the gripper is upright/aligned standardly.
                    for roll in [0]:
                         q = quaternion_from_euler(roll, base_ry, 0)
                         grasp_quats.append(q)
                    # Phase 7c: the sampled height, then higher ones (up to 8 cm) when the insertion
                    # path collides at the sampled one.
                    place_targets = [([pose[0], pose[1], float(pose[2]) + dz], [pose[0] - hover_dist, pose[1], float(pose[2]) + dz])
                                     for dz in np.arange(0.0, 0.09, 0.02)]

            else:
                # --- VERTICAL APPROACH (Top-Down) ---
                # Existing logic
                if is_box_region:
                    hover_z = pose[2] + 0.40
                elif region_name == 'placement_boundary':
                    hover_z = pose[2] + 0.35
                else:
                    hover_z = pose[2] + top_z_local + 0.12
                place_z = pose[2] + 0.015 
                
                target_pos_hover = [pose[0], pose[1], hover_z]
                target_pos_place = [pose[0], pose[1], place_z]
                
                grasp_quats = []
                import math
                def quaternion_from_euler(ai, aj, ak):
                    ai /= 2.0
                    aj /= 2.0
                    ak /= 2.0
                    ci = math.cos(ai)
                    si = math.sin(ai)
                    cj = math.cos(aj)
                    sj = math.sin(aj)
                    ck = math.cos(ak)
                    sk = math.sin(ak)
                    cc = ci*ck
                    cs = ci*sk
                    sc = si*ck
                    ss = si*sk
                    q = [cj*sc - sj*cs, cj*ss + sj*cc, cj*cs - sj*sc, cj*cc + sj*ss]
                    return q

                if is_box_region:
                    # Box placements are tight: keep top-down, but allow wrist yaw.
                    angles = np.linspace(0, 2*np.pi, 16)
                else:
                    angles = np.linspace(0, 2*np.pi, 16)

                for angle in angles:
                    q = quaternion_from_euler(np.pi, 0, angle)
                    grasp_quats.append(q)
            
            # 3. Solve IK (Phase 7c: over the place targets; one unless the cupboard
            # thin-side placement lists several heights)
            targets = place_targets or [(target_pos_place, target_pos_hover)]
            for target_pos_place, target_pos_hover in targets:
                for grasp_rot in grasp_quats:
                    try:
                        # A. Solve IK for Hover Pose
                        ik_time_ms = 150 if is_box_region else 50
                        path_configs_hover = self.robot.solve_ik_via_sampling(
                            target_pos_hover,
                            quaternion=grasp_rot,
                            max_configs=1,
                            max_time_ms=ik_time_ms,
                            ignore_collisions=True,
                        )
                        if path_configs_hover is None or len(path_configs_hover) == 0: 
                            continue
                        q_hover = path_configs_hover[0]
                    
                        # B. Solve IK for Place Pose
                        path_configs_place = self.robot.solve_ik_via_sampling(
                            target_pos_place,
                            quaternion=grasp_rot,
                            max_configs=1,
                            max_time_ms=ik_time_ms,
                            ignore_collisions=True,
                        )
                        if path_configs_place is None or len(path_configs_place) == 0: 
                            continue
                        q_place = path_configs_place[0]
                    
                        # C. Plan Hover -> Place (Linear)
                        path_down = self._get_linear_path(
                            q_hover,
                            target_pos_place,
                            grasp_rot,
                            steps=50,
                            ignore_collisions=is_box_region,
                        )
                        if not path_down: 
                            continue
                    
                        # D. Plan Place -> Hover (Linear Return)
                        path_up = self._get_linear_path(
                            q_place,
                            target_pos_hover,
                            grasp_rot,
                            steps=50,
                            ignore_collisions=is_box_region,
                        )
                        if not path_up:
                            path_down.remove()
                            continue
                        
                        # Extract configs
                        def get_configs(p):
                            return p._path_points.reshape(-1, 7).tolist()

                        t_down = get_configs(path_down)
                        t_up = get_configs(path_up)
                    
                        grasp = [0]*7
                        # Return split trajectories
                        return grasp, q_hover, q_hover, (t_down, t_up)

                    except Exception:
                        continue

            raise RuntimeError(f"Could not find valid place configuration for region {region_name}")
        finally:
            self.set_robot_conf(original_conf)

    def compute_hover_config(self, obj, pose, hover_offset=0.12):
        """Return a valid configuration q_hover strictly above the object."""
        original_conf = self.get_robot_conf()
        try:
            min_x, max_x, min_y, max_y, min_z, max_z = obj.get_bounding_box()
            # max_z is the local Z extent from origin
            top_z_local = max_z
            hover_z = pose[2] + top_z_local + hover_offset
            
            target_pos = [pose[0], pose[1], hover_z]
            
            # Sample orientations pointing down
            grasp_quats = []
            import math
            def quaternion_from_euler(ai, aj, ak):
                ai /= 2.0
                aj /= 2.0
                ak /= 2.0
                ci = math.cos(ai)
                si = math.sin(ai)
                cj = math.cos(aj)
                sj = math.sin(aj)
                ck = math.cos(ak)
                sk = math.sin(ak)
                cc = ci*ck
                cs = ci*sk
                sc = si*ck
                ss = si*sk
                q = [cj*sc - sj*cs, cj*ss + sj*cc, cj*cs - sj*sc, cj*cc + sj*ss]
                return q

            for angle in np.linspace(0, 2*np.pi, 16):
                q = quaternion_from_euler(np.pi, 0, angle)
                grasp_quats.append(q)
            
            for grasp_rot in grasp_quats:
                # Solve IK for Hover Pose
                # ignore_collisions=True for IK solving, but we check it manually after
                path_configs = self.robot.solve_ik_via_sampling(target_pos, quaternion=grasp_rot, max_configs=1, max_time_ms=50, ignore_collisions=True)
                if path_configs is not None and len(path_configs) > 0:
                    q_hover = path_configs[0]
                    # Check collision
                    self.set_robot_conf(q_hover)
                    if not self.robot.check_collision():
                        return q_hover
            
            raise RuntimeError("Could not find valid hover configuration")
        finally:
            self.set_robot_conf(original_conf)

    def compute_lid_grasp_trajectory(self, lid):
        """Compute trajectory to grasp the box lid."""
        original_conf = self.get_robot_conf()
        try:
            # 1. Get Lid Geometry
            # get_bounding_box returns [min_x, max_x, min_y, max_y, min_z, max_z] in LOCAL frame
            min_x, max_x, min_y, max_y, min_z, max_z = lid.get_bounding_box()
            
            # Get transformation matrix to convert local to world
            m_raw = lid.get_matrix()
            m = np.array(m_raw)
            # Handle flat list vs structured
            if m.ndim == 1:
                if m.size == 12: m = m.reshape(3, 4)
                elif m.size == 16: m = m.reshape(4, 4)
            
            def to_world_point(lx, ly, lz):
                # m is 3x4 or 4x4
                wx = m[0,0]*lx + m[0,1]*ly + m[0,2]*lz + m[0,3]
                wy = m[1,0]*lx + m[1,1]*ly + m[1,2]*lz + m[1,3]
                wz = m[2,0]*lx + m[2,1]*ly + m[2,2]*lz + m[2,3]
                return [wx, wy, wz]

            def to_world_vec(vx, vy, vz):
                # Rotate only
                wx = m[0,0]*vx + m[0,1]*vy + m[0,2]*vz
                wy = m[1,0]*vx + m[1,1]*vy + m[1,2]*vz
                wz = m[2,0]*vx + m[2,1]*vy + m[2,2]*vz
                return [wx, wy, wz]


            # Calculate center in local frame
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            cz = (min_z + max_z) / 2.0
            
            # User Request: Force pick the "lengthier" side.
            len_x = max_x - min_x
            len_y = max_y - min_y
            
            candidates_info = []
            # If X is longer, the faces with normal Y are the long faces (area ~ X*Z)
            if len_x >= len_y:
                candidates_info.append({'name': '-Y Face', 'pt': [cx, min_y, cz], 'app': [0, 1, 0]})
                candidates_info.append({'name': '+Y Face', 'pt': [cx, max_y, cz], 'app': [0, -1, 0]})
            else:
                candidates_info.append({'name': '-X Face', 'pt': [min_x, cy, cz], 'app': [1, 0, 0]})
                candidates_info.append({'name': '+X Face', 'pt': [max_x, cy, cz], 'app': [-1, 0, 0]})
            
            candidates = []
            for c in candidates_info:
                w_pt = to_world_point(*c['pt'])
                w_app = to_world_vec(*c['app'])
                # Normalize approach vector
                norm = np.linalg.norm(w_app)
                w_app = [x/norm for x in w_app]
                
                dist = np.linalg.norm(w_pt) # Distance from robot (0,0,0)
                candidates.append({
                    'name': c['name'],
                    'dist': dist,
                    'grasp_pt': w_pt,
                    'approach': w_app
                })
            
            # Sort by distance to robot
            # DEBUG: Check robot position
            r_pos = self.robot.get_position()
            
            # Recalculate distances relative to robot
            for c in candidates:
                c['dist'] = np.linalg.norm(np.array(c['grasp_pt']) - np.array(r_pos))

            candidates.sort(key=lambda c: c['dist'])
            
            # Try faces in order of distance
            for best_face in candidates:
                pass  # trying face: {best_face['name']}
                # print(f"DEBUG: Approach Vector: {best_face['approach']}")
                
                # Refine Grasp Point
                grasp_overlap = 0.015 
                target_pos = list(best_face['grasp_pt'])
                target_pos[0] += best_face['approach'][0] * grasp_overlap
                target_pos[1] += best_face['approach'][1] * grasp_overlap
                target_pos[2] += best_face['approach'][2] * grasp_overlap
                
                # print(f"DEBUG: Target Grasp Point: {target_pos}")

                # Generate Horizontal Grasp Quaternions
                # Z_grip = Approach
                z_axis = np.array(best_face['approach'])
                
                world_z = np.array([0, 0, 1])
                
                # Check if approach is vertical (singularity)
                if abs(np.dot(z_axis, world_z)) > 0.95:
                    y_axis_cand = np.array([1, 0, 0])
                else:
                    y_axis_cand = np.cross(z_axis, world_z)
                    y_axis_cand = y_axis_cand / np.linalg.norm(y_axis_cand)
                
                grasp_quats = []
                
                def mat2quat(M):
                    tr = M[0,0] + M[1,1] + M[2,2]
                    if tr > 0:
                        S = np.sqrt(tr+1.0) * 2
                        qw = 0.25 * S
                        qx = (M[2,1] - M[1,2]) / S
                        qy = (M[0,2] - M[2,0]) / S
                        qz = (M[1,0] - M[0,1]) / S
                    elif (M[0,0] > M[1,1]) and (M[0,0] > M[2,2]):
                        S = np.sqrt(1.0 + M[0,0] - M[1,1] - M[2,2]) * 2
                        qw = (M[2,1] - M[1,2]) / S
                        qx = 0.25 * S
                        qy = (M[0,1] + M[1,0]) / S
                        qz = (M[0,2] + M[2,0]) / S
                    elif M[1,1] > M[2,2]:
                        S = np.sqrt(1.0 + M[1,1] - M[0,0] - M[2,2]) * 2
                        qw = (M[0,2] - M[2,0]) / S
                        qx = (M[0,1] + M[1,0]) / S
                        qy = 0.25 * S
                        qz = (M[1,2] + M[2,1]) / S
                    else:
                        S = np.sqrt(1.0 + M[2,2] - M[0,0] - M[1,1]) * 2
                        qw = (M[1,0] - M[0,1]) / S
                        qx = (M[0,2] + M[2,0]) / S
                        qy = (M[1,2] + M[2,1]) / S
                        qz = 0.25 * S
                    return [qx, qy, qz, qw]

                # Vertical Fingers: X_grip is Horizontal
                x_axes_vertical = [y_axis_cand, -y_axis_cand]
                
                for x_ax in x_axes_vertical:
                    y_ax = np.cross(z_axis, x_ax)
                    y_ax = y_ax / np.linalg.norm(y_ax)
                    x_ax_final = np.cross(y_ax, z_axis)
                    
                    R = np.eye(3)
                    R[:, 0] = x_ax_final
                    R[:, 1] = y_ax
                    R[:, 2] = z_axis
                    grasp_quats.append(mat2quat(R))

                # Hover Position
                hover_dist = 0.08 
                hover_pos = [
                    target_pos[0] - z_axis[0] * hover_dist,
                    target_pos[1] - z_axis[1] * hover_dist,
                    target_pos[2] - z_axis[2] * hover_dist
                ]
                
                # --- NEW LOGIC: Slide to Edge ---
                # Shift grasp point to the edge (negative X) to maximize slide length
                x_shift = (len_x / 2.0) - 0.03 # 0.5cm margin from edge (EXTREME)
                target_pos_edge = list(target_pos)
                target_pos_edge[0] -= x_shift

                # Try IK
                z_offsets = [0, 0.01, -0.01, 0.02, -0.02, 0.03, -0.03]
                
                for i, grasp_quat in enumerate(grasp_quats):
                    for z_off in z_offsets:
                        test_hover = [hover_pos[0], hover_pos[1], hover_pos[2] + z_off]
                        test_center = [target_pos[0], target_pos[1], target_pos[2] + z_off]
                        test_edge = [target_pos_edge[0], target_pos_edge[1], target_pos_edge[2] + z_off]
                        
                        # A. Solve IK for Hover
                        path_configs_hover = self.robot.solve_ik_via_sampling(test_hover, quaternion=grasp_quat, max_configs=5, max_time_ms=100, ignore_collisions=True)
                        if path_configs_hover is None or len(path_configs_hover) == 0: 
                            continue
                        q_hover = path_configs_hover[0]

                        # VALIDATE HOVER
                        self.set_robot_conf(q_hover)
                        if self.robot.check_collision():
                            continue
                        
                        # B. Solve IK for Center (Approach)
                        path_configs_center = self.robot.solve_ik_via_sampling(test_center, quaternion=grasp_quat, max_configs=5, max_time_ms=100, ignore_collisions=True)
                        if path_configs_center is None or len(path_configs_center) == 0: 
                            continue
                        
                        # C. Solve IK for Edge (Grasp)
                        path_configs_edge = self.robot.solve_ik_via_sampling(test_edge, quaternion=grasp_quat, max_configs=5, max_time_ms=100, ignore_collisions=True)
                        if path_configs_edge is None or len(path_configs_edge) == 0: 
                            continue
                        
                        # D. Plan Hover -> Center
                        path_approach = self._get_linear_path(q_hover, test_center, grasp_quat, ignore_collisions=True)
                        if not path_approach: 
                            continue
                        
                        # E. Plan Center -> Edge
                        q_approach_end = path_approach._path_points[-7:].tolist()
                        path_slide = self._get_linear_path(q_approach_end, test_edge, grasp_quat, ignore_collisions=True)
                        if not path_slide:
                            path_approach.remove()
                            continue

                        # Validate Combined Path
                        traj_points_1 = path_approach._path_points.reshape(-1, 7).tolist()
                        traj_points_2 = path_slide._path_points.reshape(-1, 7).tolist()
                        full_traj = traj_points_1 + traj_points_2
                        
                        valid_path = True
                        for idx, q in enumerate(full_traj[:-5]):
                            self.set_robot_conf(q)
                            if self.robot.check_collision():
                                valid_path = False
                                break
                        
                        if not valid_path:
                            continue

                        q_grasp_actual = full_traj[-1]
                        
                        # Return split trajectories for precise control
                        # traj_points_1: Hover -> Center
                        # traj_points_2: Center -> Edge (Grasp)
                        return grasp_quat, q_hover, q_grasp_actual, (traj_points_1, traj_points_2)
            
            raise RuntimeError(f"Could not find valid lid grasp for any face")
            
        finally:
            self.set_robot_conf(original_conf)

    def _get_matrix_from_pose(self, pos, quat):
        # quat is [x, y, z, w] from PyRep
        # Convert to rotation matrix manually
        x, y, z, w = quat
        # Formula for quat to matrix (assuming normalized)
        # R = ...
        xx, yy, zz = x*x, y*y, z*z
        xy, xz, yz = x*y, x*z, y*z
        wx, wy, wz = w*x, w*y, w*z
        
        mat = np.array([
            [1 - 2*(yy + zz),     2*(xy - wz),     2*(xz + wy)],
            [    2*(xy + wz), 1 - 2*(xx + zz),     2*(yz - wx)],
            [    2*(xz - wy),     2*(yz + wx), 1 - 2*(xx + yy)]
        ])
        
        T = np.eye(4)
        T[:3, :3] = mat
        T[:3, 3] = pos
        return T

    def compute_open_lid_trajectory(self, lid):
        """
        Computes the full sequence: Hover -> Grasp -> Slide -> Release -> Return -> Retreat to Hover.
        Returns: grasp_quat, q_hover_start, q_hover_end, (traj_approach, traj_slide, traj_return, traj_retreat)
        """
        # 1. Compute Grasp & Approach
        # compute_lid_grasp_trajectory returns: grasp_quat, q_hover, q_grasp, (traj_hover_to_center, traj_center_to_edge)
        grasp_quat, q_hover, q_grasp, (traj_hover_to_center, traj_center_to_edge) = self.compute_lid_grasp_trajectory(lid)
        
        # Combine for full approach
        traj_approach_full = traj_hover_to_center + traj_center_to_edge
        
        # 2. Compute Slide & Return
        # compute_slide_lid_trajectory returns: q_start, q_end, traj_slide, traj_return
        # We pass q_grasp as initial_conf
        q_slide_start, q_slide_end, traj_slide, traj_return = self.compute_slide_lid_trajectory(lid, grasp_quat, initial_conf=q_grasp)
        
        # 3. Compute Retreat (Center -> Hover)
        # After traj_return, we are at Center (because we modified compute_slide_lid_trajectory to return to Center).
        # traj_hover_to_center is Hover -> Center.
        # So reverse is Center -> Hover.
        traj_retreat = traj_hover_to_center[::-1]
        
        return grasp_quat, q_hover, q_hover, (traj_approach_full, traj_slide, traj_return, traj_retreat)

    def compute_slide_lid_trajectory(self, obj, grasp_quat, initial_conf=None):
        """
        Computes a trajectory to slide the lid open in the X direction.
        """
        if initial_conf is None:
            initial_conf = self.get_robot_conf()

        # 1. Get current gripper pose (World Frame)
        old_conf = self.get_robot_conf()
        self.set_robot_conf(initial_conf)
        
        try:
            curr_tip = self.robot.arm.get_tip()
        except AttributeError:
            curr_tip = self.robot.get_tip()

        start_pos = np.array(curr_tip.get_position())
        start_quat = np.array(curr_tip.get_quaternion()) # x,y,z,w
        self.set_robot_conf(old_conf) # Restore

        # 2. Determine Slide Distance
        # Prefer a strong, uniform opening distance.
        # Keep fallback range narrow so we don't end up with tiny openings.
        min_x, max_x, min_y, max_y, min_z, max_z = obj.get_bounding_box()
        lid_len = max(max_x - min_x, max_y - min_y)

        # Target defaults can be overridden per-scene using env vars.
        # Keep the minimum fallback high to avoid under-opened lids.
        target_slide = max(
            float(os.environ.get("LID_SLIDE_TARGET_DIST", "0.30")),
            2.2 * lid_len,
        )
        min_slide = max(
            float(os.environ.get("LID_SLIDE_MIN_DIST", "0.26")),
            1.9 * lid_len,
        )

        # Ensure min is below target (narrow fallback band).
        min_slide = min(min_slide, target_slide * 0.95)
        attempts = max(3, int(os.environ.get("LID_SLIDE_ATTEMPTS", "8")))
        slide_candidates = np.linspace(target_slide, min_slide, attempts).tolist()

        for slide_dist in slide_candidates:
            slide_vec = np.array([slide_dist, 0, 0])
            target_pos = start_pos + slide_vec
            
            ratio = (slide_dist / lid_len) if lid_len > 1e-6 else 0.0
            print(
                f"DEBUG: Attempting Slide Lid by {slide_dist:.3f}m "
                f"({ratio:.2f}x lid_len) in +X direction (Lid Len: {lid_len:.3f})"
            )
            
            self.set_robot_conf(initial_conf)
            try:
                # steps=50 for smoother motion (was 15)
                path = self.robot.get_linear_path(position=target_pos, quaternion=start_quat, steps=50, ignore_collisions=True)
                
                if path:
                    traj_configs = path._path_points.reshape(-1, 7).tolist()
                    
                    # --- NEW RETURN LOGIC: Return to Center ---
                    # User Request: "return position to be... where the horizontal movement of robot is (pre-sliding motion)... like when it aligns itself to the lid face"
                    # This corresponds to the "Center" position in compute_lid_grasp_trajectory.
                    # In compute_lid_grasp_trajectory, Center = Edge + x_shift
                    # where x_shift = (len_x / 2.0) - 0.03
                    
                    x_shift = (lid_len / 2.0) - 0.03
                    return_pos = start_pos + np.array([x_shift, 0, 0])
                    
                    # Plan Return Path (Linear)
                    # We are at target_pos (end of slide). We go to return_pos.
                    # We need the config at target_pos to start the return path
                    q_slide_end = traj_configs[-1]
                    self.set_robot_conf(q_slide_end)
                    
                    path_return = self.robot.get_linear_path(position=return_pos, quaternion=start_quat, steps=30, ignore_collisions=True) # Increased to 30
                    
                    if path_return:
                        traj_return = path_return._path_points.reshape(-1, 7).tolist()
                        print(f"Slide Trajectory Computed with {len(traj_configs)} waypoints. Return path found.")
                        return traj_configs[0], traj_configs[-1], traj_configs, traj_return
                    else:
                        print("DEBUG: Return path planning failed. Using reverse slide as fallback.")
                        traj_return = traj_configs[::-1]
                        return traj_configs[0], traj_configs[-1], traj_configs, traj_return

            except Exception as e:
                print(f"DEBUG: Slide failed for distance {slide_dist:.3f}: {e}")
                continue

        print("DEBUG: Could not find valid slide trajectory for configured distance range.")
        return initial_conf, initial_conf, [], []

    def get_camera_frames(self):
        # Capture RGB from all cameras
        frames = {}
        for name, cam in self.cams.items():
            cam.handle_explicitly() # Trigger rendering
            rgb = cam.capture_rgb()
            # PyRep returns [0,1], convert to [0,255] uint8
            rgb = (rgb * 255).astype(np.uint8)
            frames[name] = rgb
        return frames

    def find_best_placement(self, obj, region_name, count=50):
        """Find a collision-free placement in region. Returns the first valid one found."""
        rng = self._placement_rng(obj, region_name)
        region_name = normalize_region_name(region_name)
        region = self.regions.get(region_name)
        if not region:
            raise ValueError(f"Region {region_name} not found")
            
        # Region bounds (Local)
        r_min_x, r_max_x, r_min_y, r_max_y, r_min_z, r_max_z = region.get_bounding_box()
        
        # Region Position (World)
        rx, ry, rz = region.get_position()
        
        # World Bounds
        world_min_x = rx + r_min_x
        world_max_x = rx + r_max_x
        world_min_y = ry + r_min_y
        world_max_y = ry + r_max_y
        
        # Search range (with some padding)
        padding = 0.05
        search_min_x = world_min_x + padding
        search_max_x = world_max_x - padding
        search_min_y = world_min_y + padding
        search_max_y = world_max_y - padding
        
        # Z height: Place on table surface if possible
        table = self.regions.get('table')
        if region_name in CUPBOARD_TARGET_REGIONS or region_name == BOX_STORAGE_REGION:
             place_z = rz + r_min_z + 0.005
        elif table:
             _, _, _, _, _, table_max_z = table.get_bounding_box()
             tz = table.get_position()[2]
             place_z = tz + table_max_z + 0.005
        else:
             place_z = rz + r_min_z + 0.005
        
        original_pose = list(obj.get_pose())

        def _collect_region_obstacles():
            obstacles = []
            region_pad_xy = float(os.environ.get("PLACEMENT_OBSTACLE_REGION_PAD_XY", "0.06"))
            region_pad_z = float(os.environ.get("PLACEMENT_OBSTACLE_REGION_PAD_Z", "0.12"))
            for name, other in getattr(self, "name_to_obj", {}).items():
                if other is None or other == obj:
                    continue
                lname = str(name).lower()
                if any(tag in lname for tag in ("boundary", "table", "cupboard", "box_base", "box_lid")):
                    continue
                try:
                    omin_x, omax_x, omin_y, omax_y, omin_z, omax_z = self._get_world_bounding_box(other)
                except Exception:
                    continue
                overlaps_region = (
                    omax_x >= (world_min_x - region_pad_xy)
                    and omin_x <= (world_max_x + region_pad_xy)
                    and omax_y >= (world_min_y - region_pad_xy)
                    and omin_y <= (world_max_y + region_pad_xy)
                    and omax_z >= (rz + r_min_z - region_pad_z)
                    and omin_z <= (rz + r_max_z + region_pad_z)
                )
                if overlaps_region:
                    obstacles.append((lname, (omin_x, omax_x, omin_y, omax_y)))
            return obstacles

        obstacle_boxes = _collect_region_obstacles()

        try:
            omin_x, omax_x, omin_y, omax_y, _, _ = obj.get_bounding_box()
            obj_half_x = max(0.01, 0.5 * abs(omax_x - omin_x))
            obj_half_y = max(0.01, 0.5 * abs(omax_y - omin_y))
        except Exception:
            obj_half_x = 0.025
            obj_half_y = 0.025

        def _violates_obstacle_keepout(sample_x, sample_y):
            # Keep-out buffers are intentionally conservative to avoid "place in front and shove" failures.
            keepout_xy = float(os.environ.get("PLACEMENT_OBSTACLE_KEEP_OUT_XY", "0.045"))
            keepout_xy_cupboard = float(os.environ.get("PLACEMENT_OBSTACLE_KEEP_OUT_XY_CUPBOARD", "0.065"))
            x_axis_bias_cupboard = float(os.environ.get("PLACEMENT_OBSTACLE_KEEP_OUT_X_BIAS_CUPBOARD", "0.03"))
            keepout = keepout_xy_cupboard if region_name in CUPBOARD_TARGET_REGIONS else keepout_xy
            for _lname, (omin_x, omax_x, omin_y, omax_y) in obstacle_boxes:
                half_x = 0.5 * abs(omax_x - omin_x)
                half_y = 0.5 * abs(omax_y - omin_y)
                dx = abs(sample_x - 0.5 * (omin_x + omax_x))
                dy = abs(sample_y - 0.5 * (omin_y + omax_y))
                min_dx = obj_half_x + half_x + keepout
                min_dy = obj_half_y + half_y + keepout
                if region_name in CUPBOARD_TARGET_REGIONS:
                    # Cupboard placements slide along +X during insertion; give extra X clearance.
                    min_dx += x_axis_bias_cupboard
                if dx < min_dx and dy < min_dy:
                    return True
            return False
        
        # Minimum distance between placed objects
        MIN_PLACEMENT_DIST = 0.06  # 6cm apart
        
        needs_hover_reachability = region_name not in CUPBOARD_TARGET_REGIONS

        if region_name in [BOX_STORAGE_REGION,  BOX_LID_TOP_REGION]:
            margin_x = 0.045
            margin_y = 0.045
            num_slots = 3
            
            box_min_x = world_min_x + margin_x
            box_max_x = world_max_x - margin_x
            box_min_y = world_min_y + margin_y
            box_max_y = world_max_y - margin_y
            
            span_x = box_max_x - box_min_x
            span_y = box_max_y - box_min_y
            
            candidate_positions = []
            if span_x >= span_y:
                xs = np.linspace(box_min_x, box_max_x, num_slots)
                for x in xs:
                    candidate_positions.append((x, 0.5 * (box_min_y + box_max_y)))
            else:
                ys = np.linspace(box_min_y, box_max_y, num_slots)
                for y in ys:
                    candidate_positions.append((0.5 * (box_min_x + box_max_x), y))
            
            # Try each deterministic slot
            for sample_x, sample_y in candidate_positions:
                if _violates_obstacle_keepout(sample_x, sample_y):
                    continue
                too_close = False
                for placed_pos in self.placed_positions:
                    dist = np.sqrt((sample_x - placed_pos[0])**2 + (sample_y - placed_pos[1])**2)
                    if dist < 0.04:  # Using smaller tolerance since it's a fixed grid
                        too_close = True
                        break
                if too_close:
                    continue
                    
                candidate_pose = [float(sample_x), float(sample_y), place_z] + original_pose[3:]
                obj.set_pose(candidate_pose)
                if not obj.check_collision():
                    if needs_hover_reachability:
                        try:
                            self.compute_hover_config(obj, candidate_pose, hover_offset=0.18)
                        except Exception:
                            pass
                        else:
                            obj.set_pose(original_pose)
                            self.placed_positions.append([sample_x, sample_y, place_z])
                            return candidate_pose
                    else:
                        obj.set_pose(original_pose)
                        self.placed_positions.append([sample_x, sample_y, place_z])
                        return candidate_pose
                        
            obj.set_pose(original_pose)
            raise RuntimeError(f"Could not find a valid deterministic placement in {region_name}")
            
        else:
            # Try random positions
            for _ in range(count):
                sample_x = rng.uniform(search_min_x, search_max_x)
                sample_y = rng.uniform(search_min_y, search_max_y)
                if _violates_obstacle_keepout(sample_x, sample_y):
                    continue
                
                # Check if too close to previously placed objects
                too_close = False
                for placed_pos in self.placed_positions:
                    dist = np.sqrt((sample_x - placed_pos[0])**2 + (sample_y - placed_pos[1])**2)
                    if dist < MIN_PLACEMENT_DIST:
                        too_close = True
                        break
                if too_close:
                    continue
                
                # Candidate pose (keep original orientation for the object)
                candidate_pose = [sample_x, sample_y, place_z] + original_pose[3:]
                
                # 1. Check Collision
                obj.set_pose(candidate_pose)
                if obj.check_collision():
                    continue
                    
                # 2. Check Hover Reachability (Downward gripper). Cupboard placement
                # uses a separate horizontal approach in the executor, so probing a
                # generic downward hover here is both redundant and can block in IK.
                if needs_hover_reachability:
                    try:
                        # We just need to know if a hover config EXISTS for this spot
                        self.compute_hover_config(obj, candidate_pose, hover_offset=0.18)
                    except Exception:
                        continue
                    obj.set_pose(original_pose)
                    self.placed_positions.append([sample_x, sample_y, place_z])
                    return candidate_pose
                obj.set_pose(original_pose)
                self.placed_positions.append([sample_x, sample_y, place_z])
                return candidate_pose
            
            # Restore
            obj.set_pose(original_pose)
            raise RuntimeError("Could not find a valid placement in region after multiple attempts")
