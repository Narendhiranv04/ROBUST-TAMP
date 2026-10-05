"""Metric definitions (plan.md Phase 1, step 5).

* Task success rate = successful trials / total trials.
* Partial goal completion = (satisfied goal relations + satisfied procedure
  checks) / (total goal relations + total procedure checks), computed per
  trial and averaged over trials.

"Total trials" is every evaluated trial of the group. Trials that ended for
infrastructure reasons (planner server down, simulator crash; termination
reason ``infrastructure``) are excluded from both metrics and counted
separately (plan.md Phase 7). A trial that ran but was not scored for another
reason counts as a failure with partial goal completion 0.

Inputs are either ``trial_end`` events from ``trial_log.jsonl`` or
``record.json`` dicts; :func:`trial_scores` normalizes both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

INFRASTRUCTURE = 'infrastructure'


@dataclass(frozen=True)
class TrialScore:
    success: bool
    satisfied: int
    total: int
    infrastructure: bool = False

    @property
    def partial_goal_completion(self) -> float:
        return self.satisfied / self.total if self.total else 0.0


def _count(value: Any) -> int:
    return int(value) if value is not None else 0


def trial_score(item: Mapping[str, Any]) -> TrialScore:
    """Score one trial from a ``trial_end`` event or a ``record.json`` dict."""
    if item.get('event') == 'trial_end':
        infrastructure = item.get('termination_reason') == INFRASTRUCTURE
        satisfied = _count(item.get('goal_relations_satisfied')) + _count(item.get('procedure_checks_satisfied'))
        total = _count(item.get('goal_relations_total')) + _count(item.get('procedure_checks_total'))
        return TrialScore(bool(item.get('success')), satisfied, total, infrastructure)
    satisfied = _count(item.get('satisfied_relation_count')) + _count(item.get('satisfied_procedure_count'))
    total = _count(item.get('required_relation_count')) + _count(item.get('required_procedure_count'))
    return TrialScore(bool(item.get('episode_success')), satisfied, total, bool(item.get('infrastructure_failure')))


def trial_scores(items: Iterable[Mapping[str, Any]]) -> List[TrialScore]:
    return [trial_score(item) for item in items]


def task_success_rate(scores: Iterable[TrialScore]) -> Optional[float]:
    evaluated = [score for score in scores if not score.infrastructure]
    if not evaluated:
        return None
    return sum(1 for score in evaluated if score.success) / len(evaluated)


def partial_goal_completion(scores: Iterable[TrialScore]) -> Optional[float]:
    evaluated = [score for score in scores if not score.infrastructure]
    if not evaluated:
        return None
    return sum(score.partial_goal_completion for score in evaluated) / len(evaluated)


def summarize(items: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    scores = trial_scores(items)
    evaluated = [score for score in scores if not score.infrastructure]
    return {
        'trials': len(scores),
        'evaluated_trials': len(evaluated),
        'infrastructure_trials': len(scores) - len(evaluated),
        'successful_trials': sum(1 for score in evaluated if score.success),
        'task_success_rate': task_success_rate(scores),
        'partial_goal_completion': partial_goal_completion(scores),
    }


__all__ = [
    'TrialScore',
    'partial_goal_completion',
    'summarize',
    'task_success_rate',
    'trial_score',
    'trial_scores',
]
