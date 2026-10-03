"""GT execution checks of the baselines: each variant's ground-truth plan, written in the baseline's
own vocabulary, carried out by the baseline's own execution code (no model).

* VLM-TAMP: the GT as the authors' subgoals (picked(o) then in/on(o, r) for a pick-place pair,
  openedjoint / closedjoint for a lid), achieved one at a time by ``execute_subgoals`` -- the same
  refinement, joint pick-place execution and checks as a real trial, with a fresh observation
  before every subgoal (a hidden object is observed by the time the GT reaches it).
* OWL-TAMP: the GT as the paper's operators, executed open-loop in one call through
  ``planning_model.forced_placements`` with OWL-TAMP's sampled (and, in the kitchen, refined) placement poses for the objects it observes at
  planning time (search-then-sample on the predicted scene); objects hidden at planning time are
  placed by the executor's own sampler.

A variant passes when the executed GT reaches the goal (trial_end success). This tests the
baselines' execution layers on every variant, not their planning.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from baselines.common import observe, parse_action_text
from baselines.owl_tamp import OWLTAMPPipeline
from baselines.vlm_tamp import VLMTAMPPipeline, space_regions
from llm_pipeline.region_aliases import planner_region_name


def gt_actions(variant_id: str) -> List[Tuple[str, ...]]:
    from llm_pipeline.oracle_trial_runner import load_gt_actions

    out = []
    for text in load_gt_actions(variant_id):
        a = parse_action_text(text)
        out.append(('place', a[1], planner_region_name(a[2])) if a[0] == 'place' else a)
    return out


class GTExecVLMTAMP(VLMTAMPPipeline):
    baseline_name = 'vlm_tamp_gt_exec'

    def run_baseline(self, goal_text: str) -> Optional[str]:
        spaces = set(space_regions(observe(self).regions))
        subgoals = []
        for a in gt_actions(self.config.variant_id):
            if a[0] == 'pick':
                subgoals.append(('picked', a[1]))
            elif a[0] == 'place':
                subgoals.append(('in' if a[2] in spaces else 'on', a[1], a[2]))
            else:
                subgoals.append(('openedjoint' if a[0] == 'open' else 'closedjoint', a[1]))
        round_trace = {'subgoals': [f"{s[0]}({', '.join(s[1:])})" for s in subgoals], 'subgoal_results': []}
        self._baseline_trace['rounds'] = [round_trace]
        failed, _ = self.execute_subgoals(subgoals, round_trace, [])
        return None if failed is None else f'GT subgoal {failed} failed'


class GTExecOWLTAMP(OWLTAMPPipeline):
    baseline_name = 'owl_tamp_gt_exec'

    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        obs = observe(self)
        spaces = set(space_regions(obs.regions))
        # a place on the broad table goes to the first named table area, as in OWL-TAMP's own plans
        # (OWLDomain.target): the GT is executed the way OWL-TAMP executes it
        from baselines.owl_tamp import OWLDomain

        table_area = OWLDomain(obs).table_area
        plan = [('place', a[1], table_area) if a[0] == 'place' and a[2] == 'table' and table_area else a
                for a in gt_actions(self.config.variant_id)]
        owl_plan = [(('place_inside' if a[2] in spaces else 'place_ontop'), a[1], a[2]) if a[0] == 'place' else a
                    for a in plan]
        # search-then-sample on the part of the plan whose objects are observed now (OWL-TAMP's input)
        known = [i for i, a in enumerate(plan) if a[0] in ('open', 'close') or a[1] in obs.objects]
        sub_plan = [plan[i] for i in known]
        geo = self.geometry(obs)
        self._initial_regions = dict(obs.objects)
        self._initial_lids = dict(obs.lids)
        names = sorted(set(obs.objects) | set(obs.regions) | set(obs.lids))
        sub_poses, failed = self.sample_plan(sub_plan, geo, names, {}, [], trace)
        poses = {known[j]: pose for j, pose in (sub_poses or {}).items()}
        trace.update({'gt_plan': [f"{a[0]}({', '.join(a[1:])})" for a in owl_plan],
                      'sampled_places': len(poses), 'sampling_failed_at': failed})
        from baselines.planning_model import forced_placements

        entries = [(plan[i][1], plan[i][2], pose) for i, pose in sorted(poses.items())]
        with forced_placements(self.env, entries, trace.setdefault('forced_placements', [])):
            outcome = self.execute(plan)
        trace['execution'] = {'success': bool(outcome.success), 'failure': outcome.error_message}
        return None if outcome.success else f'open-loop GT execution failed: {outcome.error_message}'


GT_EXEC = {'vlm_tamp': GTExecVLMTAMP, 'owl_tamp': GTExecOWLTAMP}
