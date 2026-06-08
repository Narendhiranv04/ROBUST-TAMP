from llm_pipeline.grill_geometry import (
    derive_grill_semantic_facts,
    grill_meat_status_from_facts,
    infer_grill_lid_open,
    unplaced_inside_grill_meats_from_regions,
)


class Joint:
    def __init__(self, angle):
        self.angle = angle

    def get_joint_position(self):
        return self.angle


class Env:
    def __init__(self, angle, closed=0.0):
        self.lid_joint = Joint(angle)
        self._closed_lid_angle = closed


def test_grill_semantic_facts_treat_grill_top_as_inside_grill() -> None:
    facts = derive_grill_semantic_facts(
        {
            "steak": "inside_grill",
            "steak1": "inside_grill",
            "chicken": "table",
            "phone": "plate_top",
            "chicken1": "prep_area",
            "plate": "dish_rack",
        },
        lid_open=True,
    )

    assert "grill_lid_open" in facts
    assert "inside_grill(steak)" in facts
    assert "cooked(steak)" in facts
    assert "inside_grill(steak1)" in facts
    assert "cooked(steak1)" in facts
    assert "on_table(chicken)" in facts
    assert "raw(chicken)" in facts
    assert "on_plate(phone)" not in facts
    assert not any("phone" in fact for fact in facts)
    assert "in_prep_area(chicken1)" in facts
    assert "raw(chicken1)" in facts
    assert "plate_at_dish_rack" in facts


def test_grill_semantic_facts_treat_plate_boundary_as_serving_area() -> None:
    facts = derive_grill_semantic_facts(
        {
            "plate": "plate_boundary",
            "chicken": "plate_top",
        },
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
            "close(grill_lid)",
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, plate_top)",
        ],
    )

    assert "plate_at_boundary" in facts
    assert "on_plate(chicken)" in facts


def test_grill_semantic_facts_mark_newly_placed_meat_raw_until_lid_cycle() -> None:
    facts = derive_grill_semantic_facts(
        {"chicken": "inside_grill"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
        ],
    )

    assert "inside_grill(chicken)" in facts
    assert "raw(chicken)" in facts
    assert "cooked(chicken)" not in facts


def test_grill_semantic_facts_mark_meat_cooked_after_lid_cycle_without_renaming() -> None:
    facts = derive_grill_semantic_facts(
        {"chicken": "plate_top"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
            "close(grill_lid)",
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, plate_top)",
        ],
    )

    assert "on_plate(chicken)" in facts
    assert "cooked(chicken)" in facts
    assert "cooked_chicken" not in " ".join(facts)


def test_grill_semantic_facts_mark_multiple_meats_cooked_by_shared_lid_cycle() -> None:
    facts = derive_grill_semantic_facts(
        {"chicken": "plate_top", "steak1": "plate_top"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
            "pick(steak1)",
            "place(steak1, inside_grill)",
            "close(grill_lid)",
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, plate_top)",
            "pick(steak1)",
            "place(steak1, plate_top)",
        ],
    )

    assert "cooked(chicken)" in facts
    assert "cooked(steak1)" in facts


def test_cooked_meat_stays_cooked_after_failed_plate_drop_to_table() -> None:
    facts = derive_grill_semantic_facts(
        {"steak1": "table"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(steak1)",
            "place(steak1, inside_grill)",
            "close(grill_lid)",
            "open(grill_lid)",
            "pick(steak1)",
            "place(steak1, plate_top)",
        ],
    )

    assert "on_table(steak1)" in facts
    assert "cooked(steak1)" in facts
    assert "raw(steak1)" not in facts


def test_grill_meat_status_debug_view_extracts_raw_and_cooked_facts() -> None:
    facts = [
        "grill_lid_open",
        "raw(chicken)",
        "inside_grill(chicken)",
        "cooked(steak1)",
        "plate_at_boundary",
    ]

    assert grill_meat_status_from_facts(facts) == {
        "chicken": "raw",
        "steak1": "cooked",
    }


def test_initially_cooked_meat_stays_cooked_after_it_moves_to_plate() -> None:
    facts = derive_grill_semantic_facts(
        {"steak": "plate_top"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(steak)",
            "place(steak, plate_top)",
        ],
        initially_cooked_meats={"steak"},
    )

    assert "on_plate(steak)" in facts
    assert "cooked(steak)" in facts


def test_discovered_inside_grill_meat_stays_cooked_after_move() -> None:
    discovered = unplaced_inside_grill_meats_from_regions(
        {"steak": "inside_grill", "chicken": "inside_grill"},
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
        ],
    )
    assert discovered == {"steak"}

    facts = derive_grill_semantic_facts(
        {"steak": "plate_top", "chicken": "inside_grill"},
        lid_open=True,
        completed_actions=[
            "open(grill_lid)",
            "pick(chicken)",
            "place(chicken, inside_grill)",
        ],
        initially_cooked_meats=discovered,
    )

    assert "on_plate(steak)" in facts
    assert "cooked(steak)" in facts
    assert "raw(chicken)" in facts


def test_infer_grill_lid_open_from_joint_angle() -> None:
    assert infer_grill_lid_open(Env(0.0)) is False
    assert infer_grill_lid_open(Env(0.5)) is True
