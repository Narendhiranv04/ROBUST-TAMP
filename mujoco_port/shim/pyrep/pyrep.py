"""PyRep entry point backed by MuJoCo (drop-in for pyrep.PyRep)."""

import os
import warnings
from typing import List, Tuple

import numpy as np

from pyrep.backend import sim, utils
from pyrep.backend._world import World
from pyrep.const import Verbosity
from pyrep.errors import PyRepError
from pyrep.objects.object import Object
from pyrep.objects.shape import Shape
from pyrep.textures.texture import Texture

BACKEND = 'mujoco'


class PyRep(object):
    """Used for interfacing with the (MuJoCo-emulated) CoppeliaSim scene."""

    def __init__(self):
        self.running = False
        self._world = None
        self._robot_to_count = {}
        self.connected = False
        self._handles_to_objects = {}
        self._launched = False

    def launch(self, scene_file: str = "", headless: bool = False,
               responsive_ui: bool = False, blocking: bool = False,
               verbosity: Verbosity = Verbosity.NONE) -> None:
        abs_scene_file = os.path.abspath(scene_file) if scene_file else scene_file
        if len(scene_file) > 0 and not (os.path.isfile(abs_scene_file) or os.path.isdir(abs_scene_file)):
            raise PyRepError('Scene file does not exist: %s' % scene_file)
        if os.environ.get('MUJOCO_SHIM_FORCE_HEADLESS', '0') == '1':
            headless = True
        if self._world is not None:
            self._world.close()
        self._world = World(abs_scene_file, headless=headless)
        sim._set_world(self._world)
        self._launched = True
        print(f'[mujoco-shim] Loaded {self._world.scene_dir.name} '
              f'({self._world.m.nbody} bodies, {self._world.m.ngeom} geoms, dt={self._world.dt}s, '
              f'{self._world.nsub} substeps)')

    def script_call(self, function_name_at_script_name: str,
                    script_handle_or_type: int,
                    ints=(), floats=(), strings=(), bytes='') -> (
            Tuple[List[int], List[float], List[str], str]):
        return utils.script_call(
            function_name_at_script_name, script_handle_or_type, ints, floats,
            strings, bytes)

    def _check_launched(self):
        if not self._launched:
            raise PyRepError('CoppeliaSim has not been launched. Call launch first.')

    def shutdown(self) -> None:
        self._check_launched()
        self.stop()
        self._world.close()
        self._launched = False

    def start(self) -> None:
        self._check_launched()
        if not self.running:
            sim.simStartSimulation()
            self.running = True

    def stop(self) -> None:
        self._check_launched()
        if self.running:
            sim.simStopSimulation()
            self.running = False

    def step(self) -> None:
        self._world.step()

    def step_ui(self) -> None:
        self._world._sync_viewer()

    def set_simulation_timestep(self, dt: float) -> None:
        warnings.warn('The MuJoCo backend keeps the scene timestep; '
                      'set_simulation_timestep is ignored.')

    def get_simulation_timestep(self) -> float:
        return sim.simGetSimulationTimeStep()

    def set_configuration_tree(self, config_tree) -> None:
        sim.simSetConfigurationTree(config_tree)

    def group_objects(self, objects: List[Shape]) -> Shape:
        raise PyRepError('group_objects is not supported by the MuJoCo backend.')

    def merge_objects(self, objects: List[Shape]) -> Shape:
        raise PyRepError('merge_objects is not supported by the MuJoCo backend.')

    def export_scene(self, filename: str) -> None:
        raise PyRepError('export_scene is not supported by the MuJoCo backend.')

    def import_model(self, filename: str) -> Object:
        raise PyRepError('import_model is not supported by the MuJoCo backend.')

    def create_texture(self, filename: str, interpolate=True, decal_mode=False,
                       repeat_along_u=False, repeat_along_v=False
                       ) -> Tuple[Shape, Texture]:
        raise PyRepError('create_texture is not supported by the MuJoCo backend.')

    def get_objects_in_tree(self, root_object=None, *args, **kwargs
                            ) -> List[Object]:
        return Object._get_objects_in_tree(root_object, *args, **kwargs)

    def get_collection_handle_by_name(self, collection_name: str) -> int:
        return sim.simGetCollectionHandle(collection_name)

    # MuJoCo-specific helpers -------------------------------------------------
    @property
    def mj_model(self):
        return self._world.m

    @property
    def mj_data(self):
        return self._world.d
