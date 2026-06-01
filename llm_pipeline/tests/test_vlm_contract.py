from vlm_pipeline.vlm_planner import VLMPlanner


def test_vlm_default_regions_include_canonical_plate_top() -> None:
    assert "plate_top" in VLMPlanner.KNOWN_REGIONS
    assert "inside_grill" in VLMPlanner.KNOWN_REGIONS
    assert "serving_area" in VLMPlanner.KNOWN_REGIONS
