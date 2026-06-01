from llm_pipeline.region_aliases import normalize_region_name, normalize_region_names, scene_object_for_region


def test_kitchen_region_aliases_normalize_to_public_symbols() -> None:
    assert normalize_region_name("box_boundary") == "inside_box"
    assert normalize_region_name("box-top") == "box_lid_top"
    assert normalize_region_name("box-inside") == "inside_box"
    assert normalize_region_name("cupboard_boundary") == "cupboard_shelf"
    assert normalize_region_name("cupboard_boundary_top") == "cupboard_shelf"
    assert normalize_region_name("shelf-lower") == "cupboard_shelf"


def test_normalize_region_names_deduplicates_aliases() -> None:
    assert normalize_region_names(["box_boundary", "inside_box", "box-top"]) == [
        "inside_box",
        "box_lid_top",
    ]


def test_grill_region_aliases_normalize_to_public_symbols() -> None:
    assert normalize_region_name("grill-top") == "inside_grill"
    assert normalize_region_name("grill_top") == "inside_grill"
    assert normalize_region_name("plate-boundary") == "serving_area"
    assert normalize_region_name("prep-area") == "prep_area"
    assert normalize_region_name("prep_area") == "prep_area"
    assert normalize_region_names(["grill-top", "inside_grill", "plate-boundary", "serving_area"]) == [
        "inside_grill",
        "serving_area",
    ]


def test_grill_regions_map_to_scene_objects() -> None:
    assert scene_object_for_region("inside_grill") == "grill_boundary"
    assert scene_object_for_region("grill-top") == "grill_boundary"
    assert scene_object_for_region("prep_area") == "prep_area"
    assert scene_object_for_region("plate_top") == "serving_area"
