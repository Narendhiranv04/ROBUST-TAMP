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


def test_vlm_parser_uses_strict_final_actions_block() -> None:
    planner = VLMPlanner()

    actions = planner.parse_plan(
        """
        Reasoning: inside_box is blocked until open(box_lid) is completed.
        A bad intermediate idea would be:
        open(box_lid)

        FINAL ACTIONS:
        pick(mug2)
        place(mug2, table_staging_area)
        """
    )

    assert [str(action) for action in actions] == [
        "pick(mug2)",
        "place(mug2, table_staging_area)",
    ]


def test_vlm_parser_accepts_canonical_grill_symbols() -> None:
    planner = VLMPlanner()

    actions = planner.parse_plan(
        """
        FINAL ACTIONS:
        pick(steak3)
        place(steak3, inside_grill)
        close(grill_lid)
        open(grill_lid)
        pick(chicken3)
        place(chicken3, plate_top)
        """
    )

    assert [str(action) for action in actions] == [
        "pick(steak3)",
        "place(steak3, inside_grill)",
        "close-lid(grill_lid)",
        "open-lid(grill_lid)",
        "pick(chicken3)",
        "place(chicken3, plate_top)",
    ]


def test_vlm_format_repair_prompt_is_not_box_lid_specific() -> None:
    planner = VLMPlanner()

    prompt = planner._build_format_repair_prompt(
        "visible_objects: grill_lid, chicken",
        "bad output",
    )

    assert "box_lid" not in prompt
    assert "close(lid_object)" in prompt


def test_vlm_format_repair_prompt_mentions_verbose_outputs() -> None:
    planner = VLMPlanner()
    bad_output = "Reasoning...\n" + ("still reasoning\n" * 400)

    prompt = planner._build_format_repair_prompt("visible_objects: mug2", bad_output)

    assert "too verbose" in prompt
    assert "Do not re-analyze the task" in prompt
    assert "Return only the executable action block" in prompt


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
