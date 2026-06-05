from pathlib import Path

from llm_pipeline import trial_runner


class FakePipeline:
    instances = []
    preflight_calls = 0
    run_calls = 0

    def __init__(self, config):
        self.config = config
        FakePipeline.instances.append(self)

    def initialize(self, env=None):
        self.env = env
        return True

    def preflight(self, goal_text):
        del goal_text
        type(self).preflight_calls += 1
        vision = bool(self.config.enable_vision)
        return {
            'loaded': True,
            'dry_run_plan_success': True,
            'model_type': 'vlm' if vision else 'llm',
            'text_only': not vision,
            'use_vision': vision,
            'image_present': vision,
            'image_metadata': {'image_present': vision, 'image_shapes': [[8, 15, 3]] if vision else []},
            'prompt_contract_issues': [],
            'prompt_trace': {
                'bundle': {'image_metadata': {'image_present': vision}} if vision else {},
                'system_prompt': 'system',
                'user_prompt': 'user',
            },
            'debug_snapshot': {},
        }

    def run(self, goal_text):
        del goal_text
        type(self).run_calls += 1
        vision = bool(self.config.enable_vision)
        return {
            'success': False,
            'execution_skipped': False,
            'completed_actions': [
                'pick(mug2)',
                'place(mug2, inside_box)',
                'pick(mug3)',
                'place(mug3, inside_box)',
                'pick(soup)',
                'place(soup, cupboard_shelf)',
                'pick(spam)',
                'place(spam, cupboard_shelf)',
            ],
            'final_object_region_map': {
                'mug2': 'inside_box',
                'mug3': 'inside_box',
                'soup': 'cupboard_shelf',
                'spam': 'cupboard_shelf',
            },
            'final_lid_states': {'box_lid': True},
            'cycles': [
                {
                    'cycle_number': 1,
                    'is_replan': False,
                    'failure_event': None,
                    'inference_time_s': 0.25,
                }
            ],
            'failure_reason': 'raw pipeline failure',
            'model_alias': 'fake',
            'model_type': 'vlm' if vision else 'llm',
            'prompt_mode': 'segmentation_text_image' if vision else 'segmentation_text_only',
            'text_only': not vision,
            'use_vision': vision,
            'image_present': vision,
            'image_metadata': {'image_present': vision, 'image_shapes': [[8, 15, 3]] if vision else []},
            'replan_mode': 'on',
            'pre_action_checks_enabled': True,
            'post_action_checks_enabled': True,
            'goal_check_enabled': bool(self.config.enable_goal_check),
            'total_cycles': 1,
            'total_replans': 0,
            'planner_invocations': 1,
            'total_planner_time_s': 0.25,
            'mean_planner_time_per_invocation_s': 0.25,
            'planned_actions': ['pick(mug2)', 'place(mug2, inside_box)'],
            'remaining_actions': [],
            'last_goal_check': None,
            'episode_time_s': 1.5,
        }

    def shutdown(self):
        pass


def _patch_runner(monkeypatch):
    FakePipeline.instances = []
    FakePipeline.preflight_calls = 0
    FakePipeline.run_calls = 0
    monkeypatch.setattr(trial_runner, '_configure_qt', lambda: None)
    monkeypatch.setattr(trial_runner, '_repo_setup', lambda headless, variant_spec: None)
    monkeypatch.setattr(trial_runner, '_load_variant_env', lambda variant_spec, goal_text, headless: object())
    monkeypatch.setattr(trial_runner, 'LLMOnlyReplanningPipeline', FakePipeline)


def test_trial_runner_uses_deterministic_success_and_disables_goal_check_by_default(monkeypatch, tmp_path):
    _patch_runner(monkeypatch)

    record = trial_runner.run_trial(
        variant_id='K1',
        model_alias='fake',
        icl_mode='zero_shot',
        output_dir=Path(tmp_path),
    )

    assert FakePipeline.instances[0].config.enable_goal_check is False
    assert record['goal_check_enabled'] is False
    assert record['episode_success'] is True
    assert record['raw_episode_success'] is False
    assert record['success_validation']['success'] is True
    assert record['final_object_region_map']['soup'] == 'cupboard_shelf'


def test_trial_runner_records_vlm_metadata(monkeypatch, tmp_path):
    _patch_runner(monkeypatch)

    record = trial_runner.run_trial(
        variant_id='K1',
        model_alias='fake-vlm',
        icl_mode='zero_shot',
        output_dir=Path(tmp_path),
        vision=True,
        model_type='vlm',
    )

    assert FakePipeline.instances[0].config.enable_vision is True
    assert FakePipeline.instances[0].config.text_only is False
    assert FakePipeline.instances[0].config.model_type == 'vlm'
    assert record['model_type'] == 'vlm'
    assert record['text_only'] is False
    assert record['use_vision'] is True
    assert record['image_present'] is True
    assert record['image_metadata']['image_present'] is True
    assert record['episode_success'] is True


def test_measured_trial_does_not_run_preflight(monkeypatch, tmp_path: Path) -> None:
    _patch_runner(monkeypatch)

    record = trial_runner.run_trial(
        variant_id='K1',
        model_alias='fake',
        icl_mode='zero_shot',
        output_dir=tmp_path / 'measured',
        headless=True,
    )

    assert FakePipeline.preflight_calls == 0
    assert FakePipeline.run_calls == 1
    assert record['preflight'] is None
    assert record['planner_invocations'] == 1
    assert record['total_planner_time_s'] == 0.25


def test_preflight_only_runs_preflight_without_execution(monkeypatch, tmp_path: Path) -> None:
    _patch_runner(monkeypatch)

    record = trial_runner.run_trial(
        variant_id='K1',
        model_alias='fake',
        icl_mode='zero_shot',
        preflight_only=True,
        output_dir=tmp_path / 'preflight',
        headless=True,
    )

    assert FakePipeline.preflight_calls == 1
    assert FakePipeline.run_calls == 0
    assert record['preflight_only'] is True
    assert record['preflight_success'] is True
