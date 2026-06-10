from llm_pipeline.executor import UnifiedActionBundler
from llm_pipeline.pipeline_types import DirectAction, SegmentationObjectEvidence, SegmentationSnapshot


class FakeExecutor:
    def __init__(self, snapshot):
        self.env = object()
        self.held_object = None
        self._last_action_name = None
        self.completed_primitive_actions = []
        self.snapshot = snapshot

    def _trace_bundle_state(self, *args, **kwargs):
        return self.snapshot


def test_transfer_bundle_skips_already_satisfied_object() -> None:
    snapshot = SegmentationSnapshot(
        frame_index=1,
        visible_objects=["spam"],
        newly_visible_objects=[],
        object_evidence={
            "spam": SegmentationObjectEvidence(name="spam", visible=True),
        },
        supported_regions=["cupboard_shelf"],
        object_region_map={"spam": "cupboard_shelf"},
    )
    executor = FakeExecutor(snapshot)
    bundler = UnifiedActionBundler(executor)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("GT transfer executor should not be created for a redundant bundle")

    bundler.handler.create_transfer_executor = fail_if_called

    outcome = bundler.try_execute_bundle(
        [
            DirectAction("pick", ("spam",)),
            DirectAction("place", ("spam", "cupboard_shelf")),
        ],
        index=0,
        failure_checker=None,
    )

    assert outcome.success is True
    assert outcome.consumed == 2
    assert outcome.completed_actions == ["pick(spam)", "place(spam, cupboard_shelf)"]
