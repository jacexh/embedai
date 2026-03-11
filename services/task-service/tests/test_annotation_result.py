"""Unit tests for annotation_result submit validation and state machine changes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestAnnotationResultValidation:
    """Pydantic model validates quality field."""

    def test_submit_request_requires_quality(self) -> None:
        from app.routers.tasks import SubmitTaskRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubmitTaskRequest()  # missing quality

    def test_submit_request_rejects_invalid_quality(self) -> None:
        from app.routers.tasks import SubmitTaskRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubmitTaskRequest(quality="bad_value")

    def test_submit_request_accepts_valid_quality(self) -> None:
        from app.routers.tasks import SubmitTaskRequest

        for q in ("优质数据", "可用数据", "问题数据"):
            req = SubmitTaskRequest(quality=q)
            assert req.quality == q

    def test_submit_request_notes_optional(self) -> None:
        from app.routers.tasks import SubmitTaskRequest

        req = SubmitTaskRequest(quality="优质数据")
        assert req.notes is None

        req2 = SubmitTaskRequest(quality="优质数据", notes="some note")
        assert req2.notes == "some note"


class TestStateMachineRejectedToSubmitted:
    """_TRANSITIONS must allow rejected → submitted."""

    def test_rejected_can_transition_to_submitted(self) -> None:
        from app.routers.tasks import _TRANSITIONS

        assert "submitted" in _TRANSITIONS["rejected"], (
            "rejected → submitted must be a valid transition for annotator re-submission"
        )

    def test_rejected_can_still_transition_to_assigned(self) -> None:
        from app.routers.tasks import _TRANSITIONS

        assert "assigned" in _TRANSITIONS["rejected"], (
            "rejected → assigned must still be valid for engineer re-assignment"
        )


class TestTaskOutSchema:
    """TaskOut schema must include annotation_result."""

    def test_task_out_has_annotation_result(self) -> None:
        from app.routers.tasks import TaskOut

        fields = TaskOut.model_fields
        assert "annotation_result" in fields, "TaskOut must include annotation_result field"
        # annotation_result is optional (None by default)
        assert fields["annotation_result"].default is None
