from types import SimpleNamespace

from llm_pipeline.server import LLMServer


class _RuntimeParserPlanner:
    def __init__(self):
        self.parser = None


def test_server_applies_runtime_parser_symbols_before_llm_parse() -> None:
    server = LLMServer.__new__(LLMServer)
    server.model_spec = SimpleNamespace(model_type='llm')
    server.planner = _RuntimeParserPlanner()
    server.last_request_summary = {}

    request = SimpleNamespace(
        system_prompt='system',
        user_prompt='user',
        goal='',
        icl_mode='zero_shot',
        max_new_tokens=512,
        temperature=0.0,
        held_object=None,
        use_vision=False,
        image_base64=None,
        valid_actions=['pick', 'place', 'open', 'close'],
        valid_objects=['plate', 'chicken', 'grill_lid'],
        valid_regions=['serving_area', 'inside_grill', 'plate_top'],
    )
    runtime_symbols = server._apply_runtime_parser(request)
    actions = server.planner.parser.parse('pick(plate)\nplace(plate, serving_area)')

    assert [f"{action.action_name}({', '.join(action.args)})" for action in actions] == [
        'pick(plate)',
        'place(plate, serving_area)',
    ]
    assert runtime_symbols['valid_objects'] == ['plate', 'chicken', 'grill_lid']
    assert runtime_symbols['valid_regions'] == ['serving_area', 'inside_grill', 'plate_top']
