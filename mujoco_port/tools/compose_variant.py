#!/usr/bin/env python3
"""Compose the final (Phase 3) variant scenes from extracted CoppeliaSim scenes.

    python mujoco_port/tools/compose_variant.py            # all 15 final variants
    python mujoco_port/tools/compose_variant.py K1 G1-n3   # selected ones

For each variant in ``evaluation/final_variants.py`` this copies the base scene's
extracted bundle (``mujoco_port/extracted/<base>/``), applies the edits (remove an
object and its subtree; move one; copy one from another extracted scene with new
handles, names, geometry keys and textures), writes
``mujoco_port/extracted/final_<name>/`` and builds ``mujoco_port/scenes/final_<name>/``
with ``build_mjcf``. The source ``.ttt`` files are never touched.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'mujoco_port' / 'tools'))

from evaluation.final_variants import FINAL_VARIANT_ORDER, get_final_variant  # noqa: E402

EXTRACTED = ROOT / 'mujoco_port' / 'extracted'


class Bundle:
    def __init__(self, name: str):
        self.dir = EXTRACTED / name
        self.scene = json.loads((self.dir / 'scene.json').read_text())
        with np.load(self.dir / 'geometry.npz') as data:
            self.geometry = {key: data[key] for key in data.files}

    def by_name(self, name):
        for obj in self.scene['objects']:
            if obj['name'] == name:
                return obj
        raise KeyError(f'{name} not in {self.dir.name}')

    def subtree(self, root):
        handles = {root['handle']}
        changed = True
        while changed:
            changed = False
            for obj in self.scene['objects']:
                if obj['parent'] in handles and obj['handle'] not in handles:
                    handles.add(obj['handle'])
                    changed = True
        return [obj for obj in self.scene['objects'] if obj['handle'] in handles]


def _translate(objects, delta):
    for obj in objects:
        obj['world_pos'] = [float(a + b) for a, b in zip(obj['world_pos'], delta)]


def _rename_refs(value, key_map):
    if isinstance(value, dict):
        return {k: _rename_refs(v, key_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename_refs(v, key_map) for v in value]
    if isinstance(value, str) and value in key_map:
        return key_map[value]
    return value


def _geometry_keys(value, keys, found):
    if isinstance(value, dict):
        for v in value.values():
            _geometry_keys(v, keys, found)
    elif isinstance(value, list):
        for v in value:
            _geometry_keys(v, keys, found)
    elif isinstance(value, str) and value in keys:
        found.add(value)


def _make_rigid(obj, mass):
    """Respondable dynamic convex body with the inertia of a solid box filling its bounding box."""
    shape = obj['shape']
    shape['respondable'] = True
    shape['static'] = False
    shape['geom_info']['convex'] = True
    lo, hi = np.array(obj['bbox'][:3]), np.array(obj['bbox'][3:])
    a, b, c = hi - lo
    inertia = np.diag([mass * (b * b + c * c) / 12, mass * (a * a + c * c) / 12, mass * (a * a + b * b) / 12])
    shape['mass_inertia'] = {'mass': float(mass), 'inertia': inertia.flatten().tolist(),
                             'com': ((lo + hi) / 2).tolist()}


def compose(variant_name: str, build: bool = True) -> Path:
    spec = get_final_variant(variant_name)
    if spec is None:
        raise KeyError(f'Unknown final variant {variant_name!r}')
    target = Bundle(spec.base)
    textures_out = {}
    next_handle = max(obj['handle'] for obj in target.scene['objects']) + 1000

    for edit in spec.edits:
        if edit.op == 'remove':
            doomed = {obj['handle'] for obj in target.subtree(target.by_name(edit.name))}
            target.scene['objects'] = [obj for obj in target.scene['objects'] if obj['handle'] not in doomed]
        elif edit.op == 'move':
            root = target.by_name(edit.name)
            new = [edit.xy[0], edit.xy[1], root['world_pos'][2] if edit.z is None else edit.z]
            _translate(target.subtree(root), np.array(new) - np.array(root['world_pos']))
        elif edit.op == 'copy':
            source = Bundle(edit.source_scene)
            root = source.by_name(edit.source_name)
            parts = copy.deepcopy(source.subtree(root))
            handle_map = {}
            for obj in parts:
                handle_map[obj['handle']] = next_handle
                next_handle += 1
            parent_name = next((o['name'] for o in source.scene['objects'] if o['handle'] == root['parent']), None)
            target_parent = next((o['handle'] for o in target.scene['objects'] if o['name'] == parent_name), -1)
            used = set()
            for obj in parts:
                _geometry_keys(obj, source.geometry.keys(), used)
            key_map = {key: f'{key}__c{edit.name}' for key in used}
            for key, new_key in key_map.items():
                target.geometry[new_key] = source.geometry[key]
            for obj in parts:
                old_handle = obj['handle']
                obj['handle'] = handle_map[old_handle]
                obj['parent'] = handle_map.get(obj['parent'], target_parent if old_handle == root['handle'] else -1)
                obj['name'] = (edit.name if old_handle == root['handle']
                               else obj['name'].replace(edit.source_name, edit.name, 1)
                               if edit.source_name in obj['name'] else f'{edit.name}_{obj["name"]}')
                if 'shape' in obj:
                    obj['shape'] = _rename_refs(obj['shape'], key_map)
                    for viz in obj['shape'].get('viz', []):
                        tex = viz.get('texture')
                        if tex:
                            new_tex = f'{edit.name}_{tex}'
                            textures_out[new_tex] = source.dir / 'textures' / tex
                            viz['texture'] = new_tex
            new_root = next(obj for obj in parts if obj['handle'] == handle_map[root['handle']])
            if edit.rigid_mass:
                _make_rigid(new_root, edit.rigid_mass)
            pos = [edit.xy[0], edit.xy[1], new_root['world_pos'][2] if edit.z is None else edit.z]
            _translate(parts, np.array(pos) - np.array(new_root['world_pos']))
            target.scene['objects'].extend(parts)
        else:
            raise ValueError(f'Unknown edit {edit.op!r}')

    out_name = spec.scene_dir.name
    out = EXTRACTED / out_name
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(target.dir, out, ignore=shutil.ignore_patterns('scene.json', 'geometry.npz'))
    for name, src in textures_out.items():
        shutil.copy(src, out / 'textures' / name)
    target.scene['source'] = f'composed from {spec.base} for {spec.variant_id} (evaluation/final_variants.py)'
    target.scene['fk_samples'] = target.scene.get('fk_samples')
    (out / 'scene.json').write_text(json.dumps(target.scene))
    np.savez_compressed(out / 'geometry.npz', **target.geometry)
    if build:
        from build_mjcf import SceneBuilder
        SceneBuilder(out_name).build()
    return out


def main():
    names = sys.argv[1:] or FINAL_VARIANT_ORDER
    for name in names:
        out = compose(name)
        print(f'[compose] {name} -> {out.name}')


if __name__ == '__main__':
    main()
