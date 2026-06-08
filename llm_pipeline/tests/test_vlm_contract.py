from vlm_pipeline.vlm_planner import VLMPlanner


def test_vlm_default_regions_include_canonical_plate_top() -> None:
    assert "plate_top" in VLMPlanner.KNOWN_REGIONS
    assert "inside_grill" in VLMPlanner.KNOWN_REGIONS
    assert "serving_area" in VLMPlanner.KNOWN_REGIONS


def test_vlm_parser_preserves_close_lid_actions() -> None:
    planner = VLMPlanner()

    actions = planner.parse_plan(
        """
        FINAL ACTIONS:
        close(grill_lid)
        open(grill_lid)
        """
    )

    assert [action.action_name for action in actions] == ["close-lid", "open-lid"]
    assert [action.args for action in actions] == [("grill_lid",), ("grill_lid",)]


def test_vlm_format_repair_prompt_is_not_box_lid_specific() -> None:
    planner = VLMPlanner()

    prompt = planner._build_format_repair_prompt(
        "visible_objects: grill_lid, chicken",
        "bad output",
    )

    assert "box_lid" not in prompt
    assert "close(lid_object)" in prompt


def test_vlm_chat_template_disables_thinking_when_supported() -> None:
    class Processor:
        def __init__(self):
            self.kwargs = None

        def apply_chat_template(
            self,
            messages,
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=None,
        ):
            del messages
            self.kwargs = {
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                "enable_thinking": enable_thinking,
            }
            return "templated"

    planner = VLMPlanner()
    planner.processor = Processor()

    assert planner._apply_chat_template([{"role": "user", "content": "hi"}]) == "templated"
    assert planner.processor.kwargs["enable_thinking"] is False
