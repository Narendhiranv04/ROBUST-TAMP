"""Canonical evaluation variants and benchmark defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    task_family: str
    scene_path: str
    action_sequence_length: Optional[int]
    gt_total_subtasks: Optional[int]
    gt_runner_path: Optional[str]
    goal_text: str
    expected_subtask_buckets: Dict[str, int] = field(default_factory=dict)
    model_eval_supported: bool = False
    model_eval_reason: str = ""
    pending: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            'variant_id': self.variant_id,
            'task_family': self.task_family,
            'scene_path': self.scene_path,
            'action_sequence_length': self.action_sequence_length,
            'gt_total_subtasks': self.gt_total_subtasks,
            'gt_runner_path': self.gt_runner_path,
            'goal_text': self.goal_text,
            'expected_subtask_buckets': dict(self.expected_subtask_buckets),
            'model_eval_supported': self.model_eval_supported,
            'model_eval_reason': self.model_eval_reason,
            'pending': self.pending,
        }


KITCHEN_GOAL_K1 = 'move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box'
KITCHEN_GOAL_K2 = 'move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box'
KITCHEN_GOAL_K3 = 'move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box'
GRILL_GOAL = 'COOK all raw meat using the grill and SERVE all cooked meat on the PLATE in the serving area.'
GRILL_GOAL_G1 = GRILL_GOAL
GRILL_GOAL_G2 = GRILL_GOAL
GRILL_GOAL_G3 = GRILL_GOAL


VARIANTS: Dict[str, VariantSpec] = {
    'K1': VariantSpec(
        variant_id='K1',
        task_family='kitchen',
        scene_path=str(ROOT_DIR / 'task1_variation1.ttt'),
        action_sequence_length=35,
        gt_total_subtasks=6,
        gt_runner_path=str(ROOT_DIR / 'variation_1_easy' / 'ground_truth_orchestrator_variation1_easy.py'),
        goal_text=KITCHEN_GOAL_K1,
        expected_subtask_buckets={
            'mug_to_placement': 1,
            'open_lid': 1,
            'grocery_to_cupboard': 2,
            'mug_to_box': 2,
        },
        model_eval_supported=True,
    ),
    'K2': VariantSpec(
        variant_id='K2',
        task_family='kitchen',
        scene_path=str(ROOT_DIR / 'task1_variation2.ttt'),
        action_sequence_length=35,
        gt_total_subtasks=6,
        gt_runner_path=str(ROOT_DIR / 'variation_2' / 'ground_truth_orchestrator_variation2.py'),
        goal_text=KITCHEN_GOAL_K2,
        expected_subtask_buckets={
            'mug_to_placement': 1,
            'open_lid': 1,
            'grocery_to_cupboard': 2,
            'mug_to_box': 2,
        },
        model_eval_supported=True,
    ),
    'K3': VariantSpec(
        variant_id='K3',
        task_family='kitchen',
        scene_path=str(ROOT_DIR / 'task1_variation3.ttt'),
        action_sequence_length=40,
        gt_total_subtasks=7,
        gt_runner_path=str(ROOT_DIR / 'variation_3_hard' / 'ground_truth_orchestrator_variation3_hard.py'),
        goal_text=KITCHEN_GOAL_K3,
        expected_subtask_buckets={
            'mug_to_placement': 1,
            'open_lid': 1,
            'grocery_to_cupboard': 2,
            'mug_to_box': 3,
        },
        model_eval_supported=True,
    ),
    'G1': VariantSpec(
        variant_id='G1',
        task_family='grill',
        scene_path=str(ROOT_DIR / 'grill_task2' / 'grill.variation1.ttt'),
        action_sequence_length=35,
        gt_total_subtasks=7,
        gt_runner_path=str(ROOT_DIR / 'grill_task2' / 'ground_truth_orchestrator_variation1 copy.py'),
        goal_text=GRILL_GOAL_G1,
        expected_subtask_buckets={
            'open_grill': 2,
            'close_grill': 1,
            'plate_to_boundary': 1,
            'meat_to_plate': 1,
            'meat_to_grill': 1,
            'non_target_to_table': 1,
        },
        model_eval_supported=True,
    ),
    'G2': VariantSpec(
        variant_id='G2',
        task_family='grill',
        scene_path=str(ROOT_DIR / 'grill_task2' / 'grill.variation2.ttt'),
        action_sequence_length=45,
        gt_total_subtasks=9,
        gt_runner_path=str(ROOT_DIR / 'grill_task2' / 'ground_truth_orchestrator_variation1 copy.py'),
        goal_text=GRILL_GOAL_G2,
        expected_subtask_buckets={
            'open_grill': 2,
            'close_grill': 1,
            'plate_to_boundary': 1,
            'meat_to_plate': 3,
            'meat_to_grill': 2,
        },
        model_eval_supported=True,
    ),
    'G3': VariantSpec(
        variant_id='G3',
        task_family='grill',
        scene_path=str(ROOT_DIR / 'grill_task2' / 'grill.variation3.ttt'),
        action_sequence_length=50,
        gt_total_subtasks=10,
        gt_runner_path=str(ROOT_DIR / 'grill_task2' / 'ground_truth_orchestrator_variation1 copy.py'),
        goal_text=GRILL_GOAL_G3,
        expected_subtask_buckets={
            'open_grill': 2,
            'close_grill': 1,
            'plate_to_boundary': 1,
            'meat_to_plate': 3,
            'meat_to_grill': 2,
            'non_target_to_table': 1,
        },
        model_eval_supported=True,
    ),
}


DEFAULT_GT_VARIANTS = ['K1', 'K2', 'K3', 'G1', 'G2', 'G3']
DEFAULT_MODEL_VARIANTS = ['K1', 'K2', 'K3', 'G1', 'G2', 'G3']
DEFAULT_VLM_MODEL_ALIASES = ['qwen-vl', 'gsarch', 'ms-phi4', 'internvl-3.5']
DEFAULT_LLM_MODEL_ALIASES = ['qwen', 'selene', 'deepseek-r1', 'mistral-nemo']


def _final_variant_spec(variant_id: str) -> Optional[VariantSpec]:
    """VariantSpec for a Phase 3 variant (``FINAL.K1``; evaluation/final_variants.py)."""
    from collections import Counter

    from evaluation.final_variants import final_subtasks, get_final_variant

    spec = get_final_variant(variant_id)
    if spec is None:
        return None
    buckets = dict(Counter(final_subtasks(spec.gt_actions)))
    return VariantSpec(
        variant_id=spec.variant_id,
        task_family=spec.scene,
        scene_path=str(spec.scene_dir),
        action_sequence_length=len(spec.gt_actions),
        gt_total_subtasks=sum(buckets.values()),
        gt_runner_path=None,
        goal_text=spec.goal,
        expected_subtask_buckets=buckets,
        model_eval_supported=True,
    )


def get_variant_spec(variant_id: str) -> VariantSpec:
    key = (variant_id or '').strip().upper()
    if key.startswith('FINAL.'):
        final = _final_variant_spec(key)
        if final is None:
            raise KeyError(f'Unknown variant: {variant_id}')
        return final
    if key not in VARIANTS:
        raise KeyError(f'Unknown variant: {variant_id}')
    return VARIANTS[key]
