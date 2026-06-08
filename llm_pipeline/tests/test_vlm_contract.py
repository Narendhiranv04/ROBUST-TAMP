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
