from pathlib import Path

from llm_pipeline import trial_runner


class FakePipeline:
    instances = []

    def __init__(self, config):
        self.config = config
        FakePipeline.instances.append(self)

    def initialize(self, env=None):
        return True

    def preflight(self, goal_text):
        return {
            'loaded': True,
            'dry_run_plan_success': True,
            'image_present': False,
            'prompt_contract_issues': [],
            'prompt_trace': {
                'bundle': {},
                'system_prompt': 'system',
                'user_prompt': 'user',
            },
            'debug_snapshot': {},
        }

    def run(self, goal_text):
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
            'cycles': [],
            'failure_reason': 'raw pipeline failure',
            'model_alias': 'fake',
            'prompt_mode': 'segmentation_text_only',
            'replan_mode': 'on',
            'pre_action_checks_enabled': True,
            'post_action_checks_enabled': True,
            'goal_check_enabled': bool(self.config.enable_goal_check),
        }

    def shutdown(self):
        pass


def test_trial_runner_uses_deterministic_success_and_disables_goal_check_by_default(monkeypatch, tmp_path):
    FakePipeline.instances = []
    monkeypatch.setattr(trial_runner, '_configure_qt', lambda: None)
    monkeypatch.setattr(trial_runner, '_repo_setup', lambda headless, variant_spec: None)
    monkeypatch.setattr(trial_runner, '_load_variant_env', lambda variant_spec, goal_text, headless: object())
    monkeypatch.setattr(trial_runner, 'LLMOnlyReplanningPipeline', FakePipeline)

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
