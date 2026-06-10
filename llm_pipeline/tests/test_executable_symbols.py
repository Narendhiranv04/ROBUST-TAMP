from llm_pipeline.executable_symbols import build_runtime_symbol_registry


class GrillEnv:
    grill_lid = object()
    name_to_obj = {
        "steak": object(),
        "steak1": object(),
        "chicken": object(),
        "phone": object(),
        "meat1": object(),
        "meat2": object(),
        "plate": object(),
        "grill_lid": object(),
    }

    regions = {
        "grill-top": object(),
        "inside_grill": object(),
        "prep_area": object(),
        "plate_top": object(),
        "serving_area": object(),
        "plate-boundary": object(),
        "dish_rack": object(),
        "table_staging_area": object(),
        "box_boundary": object(),
        "box-top": object(),
    }


def test_grill_symbol_registry_hides_kitchen_region_aliases() -> None:
    registry = build_runtime_symbol_registry(env=GrillEnv())

    assert registry.regions == (
        "prep_area",
        "inside_grill",
        "plate_top",
        "serving_area",
        "dish_rack",
    )


def test_grill_symbol_registry_preserves_numbered_meats_without_meat_aliases() -> None:
    registry = build_runtime_symbol_registry(env=GrillEnv())

    assert "steak" in registry.objects
    assert "steak1" in registry.objects
    assert "chicken" in registry.objects
    assert "phone" in registry.objects
    assert "meat1" not in registry.objects
    assert "meat2" not in registry.objects


def test_default_kitchen_symbol_registry_still_includes_spam() -> None:
    registry = build_runtime_symbol_registry()

    assert "spam" in registry.objects


class KitchenEnvWithLegacySoup:
    name_to_obj = {
        "mug2": object(),
        "mug3": object(),
        "soup": object(),
        "spam": object(),
        "box_lid": object(),
    }

    regions = {
        "box_boundary": object(),
        "cupboard_boundary": object(),
        "placement_boundary": object(),
    }


def test_kitchen_symbol_registry_exposes_can_of_beans_for_legacy_soup_scene() -> None:
    registry = build_runtime_symbol_registry(env=KitchenEnvWithLegacySoup())

    assert "can_of_beans" in registry.objects
    assert "soup" not in registry.objects
