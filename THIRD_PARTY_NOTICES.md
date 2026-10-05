# Third-party acknowledgments and licensing

No project-wide license was present in the source repository; none is assigned by this release. A project licensing decision remains with the authors. Inclusion here is not a statement that all assets can be redistributed under one license.

| Component | Location / source | License and status |
|---|---|---|
| PyRep Python API, Stephen James | `src/mujoco_port/shim/pyrep` | MIT; `LICENSE_PyRep.txt` retained. MuJoCo backend implementation differs from upstream. |
| PDDLStream, Caelan Garrett and contributors | `src/pddlstream`; [upstream](https://github.com/caelan/pddlstream) | Bundled revision's `LICENSE` is **GPL-3.0**, not MIT as earlier project notes claimed. Source and license retained; no Git history. |
| FastDownward | `src/pddlstream/downward` | GPL-3.0; `LICENSE.md` retained. Build compatibility flags documented. |
| Open Sans | `experiments/recording/fonts` | SIL Open Font License; notice retained. |
| VLM-TAMP | [kitchen-worlds](https://github.com/Learning-and-Intelligent-Systems/kitchen-worlds), [pybullet_planning](https://github.com/zt-yang/pybullet_planning) | Adapted/reimplemented in `src/baselines/vlm_tamp.py`; reproduced prompt material needs its source-specific redistribution terms confirmed. |
| OWL-TAMP | [paper](https://arxiv.org/abs/2411.08253) | Paper-based reimplementation in `src/baselines/owl_tamp.py` and `owl_constraints.py`; no official code source established by this release. |
| Inner Monologue | [project and paper](https://innermonologue.github.io/) | Paper-based adapted prompt and feedback loop in `src/baselines/inner_monologue.py`; not official code. |
| EPoG | [official repository](https://github.com/buaa-colalab/EPoG) | Apache-2.0 upstream; adapted/reimplemented prompts and graph planning, without lost-object estimation. |
| Scene models, meshes and textures | `assets/scenes`, converted from original CoppeliaSim/RLBench scene assets | Original asset redistribution permissions require author confirmation; preserved geometry is not newly licensed here. |
| MuJoCo and vLLM | Installed separately | Apache-2.0 upstream; consult their distributions. |
| Checkpoints | Official model-card links in `experiments/docs/models.md` | Per-model terms and access restrictions; no weights bundled. |
| Animation dependencies | Embedded in `assets/media/*.html` | React, ReactDOM and Babel resources retain their embedded notices; original HTMLs retained with identifying image metadata removed. |

Public third-party author names and copyright notices are intentional scientific attribution. They are not submission-author identities. The supplementary document retains the conference class and its notices.
