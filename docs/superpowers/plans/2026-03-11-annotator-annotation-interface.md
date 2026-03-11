# Annotator Annotation Interface Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an annotation sidebar to the MCAP preview page so annotators can rate data quality (优质/可用/问题) and submit their annotation without leaving the platform.

**Architecture:** Backend adds `annotation_result` JSONB column to `annotation_tasks`, extends the submit endpoint to accept and validate a quality rating, and adds `rejected → submitted` as a valid state transition. Frontend adds a new `AnnotationSidebar` component rendered in `PreviewPage` when a `task_id` query param is present; `TasksPage` navigation buttons are updated to carry `task_id` and the redundant direct-submit buttons are removed.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React 19 + TanStack Query + Tailwind CSS + React Router v6 (frontend), pytest + httpx (E2E tests), Alembic (migrations).

---

## Chunk 1: Backend — Migration, Model, State Machine & Router

### Task 1: DB migration — add `annotation_result` column

**Files:**
- Create: `shared/migrations/versions/004_annotation_tasks_result.py`

- [ ] **Step 1: Write the migration file**

```python
"""Add annotation_result to annotation_tasks.

Revision ID: 004
Revises: 003
Create Date: 2026-03-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotation_tasks",
        sa.Column("annotation_result", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotation_tasks", "annotation_result")
```

- [ ] **Step 2: Run migration**

```bash
cd /home/xuhao/embedai
make migrate
```

Expected: `Running upgrade 003 -> 004, Add annotation_result to annotation_tasks`

- [ ] **Step 3: Commit**

```bash
git add shared/migrations/versions/004_annotation_tasks_result.py
git commit -m "feat: add annotation_result column to annotation_tasks (migration 004)"
```

---

### Task 2: ORM model — add `annotation_result` field

**Files:**
- Modify: `services/task-service/app/models.py` (line 97, after `updated_at`)

- [ ] **Step 1: Add field to `AnnotationTask` class**

In `services/task-service/app/models.py`, after line 97 (`updated_at: Mapped[datetime | None]...`), add:

```python
    annotation_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

`JSONB` is already imported at line 8 (`from sqlalchemy.dialects.postgresql import JSONB, UUID`). No new import needed.

- [ ] **Step 2: Verify no syntax errors**

```bash
cd /home/xuhao/embedai/services/task-service
python -c "from app.models import AnnotationTask; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/task-service/app/models.py
git commit -m "feat: add annotation_result field to AnnotationTask ORM model"
```

---

### Task 3: Router — state machine, TaskOut schema, submit endpoint

**Files:**
- Modify: `services/task-service/app/routers/tasks.py`

- [ ] **Step 1: Write the failing tests first**

Create `services/task-service/tests/test_annotation_result.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/xuhao/embedai/services/task-service
python -m pytest tests/test_annotation_result.py -v 2>&1 | head -40
```

Expected: Several FAILED or ImportError (SubmitTaskRequest not defined yet, _TRANSITIONS missing "submitted", TaskOut missing annotation_result).

- [ ] **Step 3: Apply all router changes**

In `services/task-service/app/routers/tasks.py`, make these changes:

**3a. Add `Literal` to imports** (modify the `from typing import` line, currently reads `from typing import Annotated`):

```python
from typing import Annotated, Literal
```

**3b. Update `_TRANSITIONS` dict** (line 35, change `rejected` entry):

```python
_TRANSITIONS: dict[str, set[str]] = {
    "created": {"assigned"},
    "assigned": {"submitted", "created"},  # created = unassign
    "submitted": {"approved", "rejected"},
    "rejected": {"assigned", "submitted"},  # submitted = direct re-submit by annotator
    "approved": set(),
}
```

Also update the docstring at the top of the file (lines 4-5) to reflect new transition:

```python
"""Annotation task management API — Task 5.2.

State machine (ADR H4):
  created → assigned → submitted → approved
                    ↘            ↗
                     rejected → assigned  (re-assign for rework)
                     rejected → submitted (annotator direct re-submit)
"""
```

**3c. Add `SubmitTaskRequest` class** after `RejectRequest` (after line 104):

```python
class SubmitTaskRequest(BaseModel):
    quality: Literal["优质数据", "可用数据", "问题数据"]
    notes: str | None = None
```

**3d. Add `annotation_result` to `TaskOut`** (after `updated_at` field, line 121):

```python
    annotation_result: dict | None = None
```

**3e. Add `annotation_result` to `_task_out()` helper** (add after `updated_at` line in the dict, line 153):

```python
        "annotation_result": task.annotation_result,
```

**3f. Update `submit_task` endpoint signature and body** (replace lines 279-306):

```python
@router.post("/tasks/{task_id}/submit", response_model=TaskOut)
async def submit_task(
    task_id: uuid.UUID,
    body: SubmitTaskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AnnotationTask).where(AnnotationTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    # Annotator can only submit their own task
    if (
        current_user.role not in ("admin", "engineer")
        and str(task.assigned_to) != current_user.user_id
    ):
        raise HTTPException(status_code=403, detail="not assigned to this task")

    _assert_transition(task.status, "submitted")

    task.status = "submitted"
    task.annotation_result = {"quality": body.quality, "notes": body.notes}
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_out(task)
```

- [ ] **Step 4: Run the unit tests to verify they pass**

```bash
cd /home/xuhao/embedai/services/task-service
python -m pytest tests/test_annotation_result.py -v
```

Expected: All tests PASSED.

- [ ] **Step 5: Update existing E2E test helpers that call submit without a body**

The existing `tests/e2e/test_annotation_workflow.py` has **five** submit calls without a body. All will now return 422. Update each one:

**Call 1 — `_run_full_approve` helper (line 33).** Change:
```python
    resp = await client.task.post(f"/api/v1/tasks/{task_id}/submit")
```
to:
```python
    resp = await client.task.post(
        f"/api/v1/tasks/{task_id}/submit",
        json={"quality": "优质数据"},
    )
```

**Call 2 — `TestFullApproveWorkflow.test_full_approve_workflow` (line 76).** Change:
```python
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
```
to:
```python
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
```

**Calls 3 & 4 — `TestRejectionAndReworkCycle.test_full_rejection_and_rework_cycle`** (initial submit and re-submit after re-assign). Change each bare submit call to include a body:
```python
        # Call 3 — initial submit
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        # ... (existing assert unchanged)

        # Call 4 — re-submit after re-assign
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        # ... (existing assert unchanged)
```

**Call 5 — terminal-state check** at the end of `test_full_rejection_and_rework_cycle`. This call intentionally tests that re-submitting an `approved` task fails. Add a body so the failure comes from the state machine (409) not from missing body (422):
```python
        # Only update the post() call — the assert on the next line stays unchanged
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        # existing assert stays: assert resp.status_code in (400, 409, 422), ...
```

- [ ] **Step 6: Commit**

```bash
git add services/task-service/app/routers/tasks.py \
        services/task-service/tests/test_annotation_result.py \
        tests/e2e/test_annotation_workflow.py
git commit -m "feat: extend submit endpoint with quality rating and update state machine"
```

---

### Task 4: E2E tests for annotation result

**Files:**
- Modify: `tests/e2e/test_annotation_workflow.py` (add new test class at bottom)

- [ ] **Step 1: Add missing imports at the top of `tests/e2e/test_annotation_workflow.py`**

The existing file imports only `pytest` and `E2EClient`. The new 403 test requires `httpx` and the service URLs from `conftest`. Add at the top of the file after the existing imports:

```python
import httpx

from tests.e2e.conftest import GATEWAY_URL, TASK_SERVICE_URL
```

Or simply define the URLs inline since conftest doesn't export them — use the same defaults:

```python
import httpx

GATEWAY_URL = "http://localhost:8000"
TASK_SERVICE_URL = "http://localhost:8002"
```

- [ ] **Step 2: Add new test class**

Append to the end of `tests/e2e/test_annotation_workflow.py`:

```python
@pytest.mark.e2e
class TestAnnotationResult:
    """Submit stores annotation_result; validation; re-submission overwrites."""

    async def test_submit_with_quality_stores_annotation_result(
        self, gateway_client: E2EClient
    ) -> None:
        # Create and assign task
        task_id = await _create_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200

        # Submit with quality + notes
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "clean sensor data"},
        )
        assert resp.status_code == 200, f"Submit failed: {resp.text}"
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["annotation_result"] is not None
        assert body["annotation_result"]["quality"] == "优质数据"
        assert body["annotation_result"]["notes"] == "clean sensor data"

    async def test_submit_without_notes_stores_null_notes(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 200
        assert resp.json()["annotation_result"]["quality"] == "可用数据"
        assert resp.json()["annotation_result"]["notes"] is None

    async def test_submit_missing_quality_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_submit_invalid_quality_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "bad_value"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_submit_no_body_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_rejected_task_can_resubmit_directly(
        self, gateway_client: E2EClient
    ) -> None:
        # Create → assign → submit → reject
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "needs correction"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Re-submit directly from rejected (no re-assign needed)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "corrected"},
        )
        assert resp.status_code == 200, f"Re-submit from rejected failed: {resp.text}"
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["annotation_result"]["quality"] == "优质数据"
        assert body["annotation_result"]["notes"] == "corrected"

    async def test_resubmit_overwrites_annotation_result(
        self, gateway_client: E2EClient
    ) -> None:
        # submit with quality A, reject, re-submit with quality B
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "问题数据", "notes": "first attempt"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "fix it"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "second attempt"},
        )

        # Verify via GET that result is overwritten
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        result = resp.json()["annotation_result"]
        assert result["quality"] == "优质数据", f"Expected 优质数据, got {result['quality']}"
        assert result["notes"] == "second attempt"

    async def test_submitted_task_cannot_resubmit(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 7: submitted → submitted is blocked (409 from state machine)."""
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 (state machine) resubmitting a submitted task, got {resp.status_code}: {resp.text}"
        )

    async def test_approved_task_cannot_submit(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 8: approved → submitted is blocked (409 from state machine)."""
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 (state machine) submitting an approved task, got {resp.status_code}: {resp.text}"
        )

    async def test_annotator_cannot_submit_others_task(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 9: annotator submitting another user's task gets 403.

        Strategy: register a second annotator, assign the task to the first
        annotator (gateway_client), then try to submit as the second annotator.
        """
        import uuid as _uuid

        project_id = gateway_client.project_id
        unique = _uuid.uuid4().hex[:8]

        # Register a second annotator user
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as raw:
            resp = await raw.post(
                "/auth/register",
                json={
                    "email": f"annotator2_{unique}@test.local",
                    "password": "ann_pass_123",
                    "name": f"Annotator Two {unique}",
                    "role": "annotator",
                    "project_id": project_id,
                },
            )
            assert resp.status_code in (200, 201), f"Register failed: {resp.text}"
            resp2 = await raw.post(
                "/auth/login",
                json={"email": f"annotator2_{unique}@test.local", "password": "ann_pass_123"},
            )
            assert resp2.status_code == 200
            token2 = resp2.json()["token"]

        # Create task and assign to gateway_client (admin user, acting as first annotator)
        task_id = await _create_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200

        # Try to submit as annotator2 — should get 403
        headers2 = {"Authorization": f"Bearer {token2}"}
        async with httpx.AsyncClient(
            base_url=TASK_SERVICE_URL, headers=headers2, timeout=30.0
        ) as ts2:
            resp = await ts2.post(
                f"/api/v1/tasks/{task_id}/submit",
                json={"quality": "优质数据"},
            )
        assert resp.status_code == 403, (
            f"Expected 403 when annotator submits another's task, got {resp.status_code}: {resp.text}"
        )

    async def test_rejected_to_assigned_still_valid(
        self, gateway_client: E2EClient
    ) -> None:
        # Engineer can still re-assign a rejected task
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "redo"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Re-assign from rejected failed: {resp.text}"
        assert resp.json()["status"] == "assigned"
```

- [ ] **Step 3: Run E2E tests (backend only)**

```bash
cd /home/xuhao/embedai
make e2e-up
make e2e-module MODULE=annotation_workflow
```

Expected: All tests in `TestAnnotationResult` pass. Existing tests in `TestFullApproveWorkflow`, `TestRejectionAndReworkCycle`, `TestTaskToDatasetVersionPipeline` also pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_annotation_workflow.py
git commit -m "test: add E2E tests for annotation_result quality rating workflow"
```

---

## Chunk 2: Frontend — API Types & TasksPage

### Task 5: Update `api/tasks.ts`

**Files:**
- Modify: `web/src/api/tasks.ts`

- [ ] **Step 1: Update `AnnotationTask` interface** — add `annotation_result` field

Replace the entire `AnnotationTask` interface (lines 4-19) with:

```typescript
export interface AnnotationTask {
  id: string;
  project_id: string;
  episode_id: string | null;
  dataset_version_id: string | null;
  type: string;
  guideline_url: string | null;
  required_skills: string[];
  deadline: string | null;
  status: "created" | "assigned" | "submitted" | "approved" | "rejected";
  assigned_to: string | null;
  label_studio_task_id: number | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  annotation_result: {
    quality: "优质数据" | "可用数据" | "问题数据";
    notes: string | null;
  } | null;
}
```

- [ ] **Step 2: Update `useSubmitTask`** — change signature from plain `taskId: string` to payload object

Replace lines 85-91 with:

```typescript
interface SubmitTaskPayload {
  taskId: string;
  quality: string;
  notes?: string;
}

export function useSubmitTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, quality, notes }: SubmitTaskPayload) =>
      apiClient.post(`/tasks/${taskId}/submit`, { quality, notes }),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["task", taskId] });
    },
  });
}
```

- [ ] **Step 3: Add `useTask` hook** — append after `useSubmitTask`:

```typescript
export function useTask(taskId: string) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: async () => {
      const { data } = await apiClient.get<AnnotationTask>(`/tasks/${taskId}`);
      return data;
    },
    enabled: !!taskId,
  });
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /home/xuhao/embedai/web
npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors (or only pre-existing unrelated errors).

- [ ] **Step 5: Commit**

```bash
git add web/src/api/tasks.ts
git commit -m "feat: add annotation_result type, update useSubmitTask, add useTask hook"
```

---

### Task 6: Update `TasksPage.tsx` — annotator view

**Files:**
- Modify: `web/src/pages/TasksPage.tsx`

The `AnnotatorTasksView` component (lines 113-226) needs:
1. Remove `useSubmitTask` import usage and `handleSubmit` function
2. Change "查看数据" button to navigate with `task_id`
3. Replace direct-submit buttons with navigation buttons

- [ ] **Step 1: Update `AnnotatorTasksView`**

Replace the entire `AnnotatorTasksView` function (lines 113-226) with:

```typescript
function AnnotatorTasksView({ userId }: { userId: string }) {
  const [activeTab, setActiveTab] = useState("assigned");
  const { data: tasks = [], isLoading } = useTasks({ status: activeTab, assigned_to: userId });
  const navigate = useNavigate();

  const handleOpenAnnotation = (task: AnnotationTask) => {
    navigate(`/preview/${task.episode_id}?task_id=${task.id}`);
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">我的标注任务</h1>

      <div className="flex border-b border-gray-200 mb-4">
        {ANNOTATOR_STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.value
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : tasks.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg">暂无{STATUS_LABELS[activeTab] ?? ""}任务</p>
          <p className="text-sm mt-1">请联系工程师分配任务</p>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <div
              key={task.id}
              className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_COLORS[task.status] ?? "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {STATUS_LABELS[task.status] ?? task.status}
                  </span>
                  <span className="text-xs text-gray-500">{task.type}</span>
                </div>
                <p className="font-mono text-xs text-gray-600 truncate">
                  {task.dataset_version_id ?? task.episode_id ?? task.id}
                </p>
                {task.deadline && (
                  <p className="text-xs text-gray-400 mt-1">
                    截止：{new Date(task.deadline).toLocaleDateString("zh-CN")}
                  </p>
                )}
                {task.guideline_url && (
                  <a
                    href={task.guideline_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-blue-600 hover:underline mt-1 inline-block"
                  >
                    查看标注指南 →
                  </a>
                )}
                {task.annotation_result && (
                  <p className="text-xs text-gray-400 mt-1">
                    已评级：<span className="font-medium text-gray-600">{task.annotation_result.quality}</span>
                  </p>
                )}
              </div>
              <div className="ml-4 shrink-0">
                {task.episode_id && task.status === "assigned" && (
                  <button
                    onClick={() => handleOpenAnnotation(task)}
                    className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                  >
                    开始标注
                  </button>
                )}
                {task.episode_id && task.status === "rejected" && (
                  <button
                    onClick={() => handleOpenAnnotation(task)}
                    className="px-4 py-2 text-sm bg-orange-600 text-white rounded hover:bg-orange-700"
                  >
                    重新提交
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Remove unused `useSubmitTask` import from `TasksPage.tsx`**

At line 6, change:
```typescript
  useTasks,
  useAnnotatorsWithWorkload,
  useAssignTask,
  useSubmitTask,
  type AnnotationTask,
  type UserWorkload,
```
to:
```typescript
  useTasks,
  useAnnotatorsWithWorkload,
  useAssignTask,
  type AnnotationTask,
  type UserWorkload,
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/xuhao/embedai/web
npx tsc --noEmit 2>&1 | head -30
```

Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/TasksPage.tsx
git commit -m "feat: update annotator task list to navigate to annotation page with task_id"
```

---

## Chunk 3: Frontend — AnnotationSidebar & PreviewPage

### Task 7: Create `AnnotationSidebar` component

**Files:**
- Create: `web/src/components/AnnotationSidebar.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTask, useSubmitTask } from "@/api/tasks";
import { Spinner } from "@/components/Spinner";
import { toast } from "@/store/toast";

interface AnnotationSidebarProps {
  taskId: string;
}

const QUALITY_OPTIONS = [
  { value: "优质数据", icon: "✅", color: "border-green-500 bg-green-50 text-green-700" },
  { value: "可用数据", icon: "⚠️", color: "border-yellow-500 bg-yellow-50 text-yellow-700" },
  { value: "问题数据", icon: "❌", color: "border-red-500 bg-red-50 text-red-700" },
] as const;

const IDLE_BTN = "border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:bg-gray-50";

export function AnnotationSidebar({ taskId }: AnnotationSidebarProps) {
  const navigate = useNavigate();
  const { data: task, isLoading, isError } = useTask(taskId);
  const { mutate: submitTask, isPending } = useSubmitTask();

  const [quality, setQuality] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  // Pre-fill from previous annotation_result (rejected re-submission)
  useEffect(() => {
    if (task?.annotation_result) {
      setQuality(task.annotation_result.quality);
      setNotes(task.annotation_result.notes ?? "");
    }
  }, [task?.annotation_result]);

  const handleSubmit = () => {
    if (!quality) return;
    submitTask(
      { taskId, quality, notes: notes.trim() || undefined },
      {
        onSuccess: () => {
          toast.success("标注已提交，等待审核");
          navigate("/tasks");
        },
        onError: () => {
          // error toast shown by apiClient interceptor
        },
      }
    );
  };

  if (isLoading) {
    return (
      <aside className="w-[216px] shrink-0 border-l border-gray-200 bg-white flex items-center justify-center">
        <Spinner />
      </aside>
    );
  }

  if (isError || !task) {
    return (
      <aside className="w-[216px] shrink-0 border-l border-gray-200 bg-white p-4">
        <p className="text-sm text-red-500">加载任务信息失败</p>
      </aside>
    );
  }

  const isRejected = task.status === "rejected";

  return (
    <aside className="w-[216px] shrink-0 border-l border-gray-200 bg-white flex flex-col overflow-y-auto">
      {/* Task info */}
      <div className="p-4 border-b border-gray-100">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">
          任务信息
        </p>
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">类型</span>
            <span className="text-gray-700 font-medium">{task.type}</span>
          </div>
          {task.deadline && (
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">截止</span>
              <span className="text-red-500 font-medium">
                {new Date(task.deadline).toLocaleDateString("zh-CN")}
              </span>
            </div>
          )}
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">状态</span>
            <span className={`font-medium ${isRejected ? "text-red-600" : "text-blue-600"}`}>
              {isRejected ? "已驳回" : "进行中"}
            </span>
          </div>
        </div>
        {task.guideline_url && (
          <a
            href={task.guideline_url}
            target="_blank"
            rel="noreferrer"
            className="mt-3 text-xs text-blue-600 hover:underline flex items-center gap-1"
          >
            📋 查看标注指南
          </a>
        )}
        {isRejected && (
          <p className="mt-2 text-xs text-orange-600 bg-orange-50 rounded p-2">
            任务已被驳回，请修改后重新提交
          </p>
        )}
      </div>

      {/* Quality rating */}
      <div className="p-4 border-b border-gray-100 flex-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">
          质量评级
        </p>
        <div className="space-y-2">
          {QUALITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setQuality(opt.value)}
              className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                quality === opt.value ? opt.color : IDLE_BTN
              }`}
            >
              <span>{opt.icon}</span>
              <span>{opt.value}</span>
            </button>
          ))}
        </div>

        {/* Notes */}
        <div className="mt-4">
          <label className="block text-xs text-gray-500 mb-1.5">备注（可选）</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="描述数据特点或问题..."
            rows={4}
            className="w-full text-xs border border-gray-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400 text-gray-700 placeholder-gray-300"
          />
        </div>
      </div>

      {/* Submit */}
      <div className="p-4">
        <button
          onClick={handleSubmit}
          disabled={!quality || isPending}
          className="w-full py-2.5 text-sm font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "提交中..." : "提交标注"}
        </button>
        <p className="mt-2 text-center text-xs text-gray-400">
          {isRejected ? "提交将覆盖上次评级" : "提交后无法修改评级"}
        </p>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/xuhao/embedai/web
npx tsc --noEmit 2>&1 | head -30
```

Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/AnnotationSidebar.tsx
git commit -m "feat: add AnnotationSidebar component with quality rating and submit"
```

---

### Task 8: Update `PreviewPage.tsx` — add sidebar when task_id is present

**Files:**
- Modify: `web/src/pages/PreviewPage.tsx`

- [ ] **Step 1: Add imports**

**1a.** Merge `useSearchParams` into the existing `react-router-dom` import (line 4 of `PreviewPage.tsx`). Change:
```typescript
import { useParams, useNavigate } from "react-router-dom";
```
to:
```typescript
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
```

**1b.** Add `AnnotationSidebar` import after the other component imports:
```typescript
import { AnnotationSidebar } from "@/components/AnnotationSidebar";
```

> **Prerequisite:** Task 7 (`AnnotationSidebar.tsx`) must be committed before this step compiles.

- [ ] **Step 2: Read `task_id` from URL** — add inside `PreviewPage()` function body, right after the existing `const navigate = useNavigate();` line:

```typescript
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get("task_id");
```

- [ ] **Step 3: Update the main content layout** — replace the `return` JSX (lines 194-241). The change wraps the existing content in a flex-row div when `taskId` is present and appends `AnnotationSidebar`. Replace the entire `return` statement:

```tsx
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(taskId ? "/tasks" : "/episodes")}
              className="text-gray-600 hover:text-gray-900"
            >
              ← {taskId ? "返回任务列表" : "Back"}
            </button>
            <h1 className="text-xl font-semibold text-gray-900">
              {episode.filename}
            </h1>
            {taskId && (
              <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 rounded">
                标注任务
              </span>
            )}
          </div>
          <div className="text-sm text-gray-500">
            Duration: {Math.floor(duration / 60)}m {Math.floor(duration % 60)}s
          </div>
        </div>
      </div>

      {/* Main content — flex row when annotation sidebar present */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 min-w-0 p-6 overflow-auto">
          <div className="max-w-7xl mx-auto">
            {/* Video grid */}
            <div className="mb-6">
              <VideoGrid
                topics={imageTopics}
                frames={frames}
                isLoading={isLoadingFrames}
              />
            </div>

            {/* Timeline */}
            <TimelineControl
              currentTime={currentTime}
              duration={duration}
              isPlaying={isPlaying}
              playbackRate={playbackRate}
              onSeek={handleSeek}
              onPlay={handlePlay}
              onPause={handlePause}
              onRateChange={setPlaybackRate}
            />
          </div>
        </div>

        {taskId && <AnnotationSidebar taskId={taskId} />}
      </div>
    </div>
  );
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /home/xuhao/embedai/web
npx tsc --noEmit 2>&1 | head -30
```

Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/PreviewPage.tsx
git commit -m "feat: add annotation sidebar to MCAP preview page when task_id param present"
```

---

### Task 9: Build and smoke test

- [ ] **Step 1: Build frontend**

```bash
cd /home/xuhao/embedai/web
npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Start all services**

```bash
cd /home/xuhao/embedai
make e2e-up
```

Expected: All containers healthy.

- [ ] **Step 3: Run full E2E suite**

```bash
cd /home/xuhao/embedai
make e2e
```

Expected: All tests pass, including the new `TestAnnotationResult` class.

- [ ] **Step 4: Manual smoke test (optional but recommended)**

1. Create a test annotator account via the registration API or browser (role: `annotator`)
2. As an admin, create a task and assign it to the annotator
3. Log in as the annotator, go to 我的任务 — see the task with "开始标注" button
4. Click "开始标注" — URL should be `/preview/{episodeId}?task_id={taskId}`
5. Annotation sidebar appears on the right
6. Select "优质数据", add a note, click "提交标注"
7. Redirected back to `/tasks`, task appears in "已提交" tab with rating shown

- [ ] **Step 5: Final commit (if any loose files)**

```bash
git status
# commit any remaining changes
```
