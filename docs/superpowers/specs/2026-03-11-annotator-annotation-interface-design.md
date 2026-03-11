# 标注员标注界面设计文档

**日期：** 2026-03-11
**状态：** 已确认
**作者：** Claude (brainstorming session)

---

## 背景

标注员目前可以在平台查看任务列表、跳转 MCAP 预览页查看数据，但没有在平台内完成标注的工具。本次需求在 MCAP 预览页右侧增加标注侧边栏，使标注员可以直接在平台内对数据进行质量评级并提交。

---

## 功能范围

### 在范围内
- 标注员在 MCAP 预览页右侧看到标注侧边栏
- 侧边栏显示任务信息（类型、截止日、状态、标注指南链接）
- 质量评级三档：**优质数据 / 可用数据 / 问题数据**
- 可选文字备注
- 提交标注（带评级数据），提交后跳回任务列表
- 驳回后重新提交：预填上次评级，覆盖写入
- 任务列表"查看数据/开始标注"按钮携带 `task_id` 跳转到预览页
- 任务列表移除直接提交按钮（提交统一在侧边栏完成）

### 不在范围内
- Label Studio 集成（已有基础，但本次不启用）
- 时间段事件标注
- 场景属性标签
- 1-5 分数值评分
- `submitted`/`approved` 状态的评级修改

---

## 设计方案

### 整体布局

MCAP 预览页（`/preview/{episodeId}?task_id={taskId}`）：
- 左侧：原有 6 路相机视频网格 + 时间轴（不改动）
- 右侧：新增 `AnnotationSidebar` 组件（固定 216px 宽）
- 仅当 URL 中存在 `task_id` 参数时渲染侧边栏（非标注场景不显示，布局不变）

### 用户流程

**正常提交（assigned）：**
```
任务列表 → 点"开始标注"
  → /preview/{episodeId}?task_id={taskId}
  → 加载任务详情（GET /tasks/{taskId}）
  → 观看视频 → 选质量评级（必选）→ 填备注（可选）
  → 点"提交标注"
  → POST /tasks/{taskId}/submit { quality, notes }
  → 成功后跳回 /tasks
```

**驳回后重新提交（rejected）：**
```
任务列表"已驳回"Tab → 点"重新提交"
  → /preview/{episodeId}?task_id={taskId}
  → 侧边栏预填上次 annotation_result（quality + notes）
  → 修改评级/备注 → 点"提交标注"
  → POST /tasks/{taskId}/submit { quality, notes }（覆盖 annotation_result）
  → 成功后跳回 /tasks
```

---

## 后端变更

### 1. 数据库迁移

新增迁移文件：`shared/migrations/versions/004_annotation_tasks_result.py`
（当前最新迁移为 `003_annotation_tasks_episode_id.py`，004 是下一个）

```sql
ALTER TABLE annotation_tasks
ADD COLUMN annotation_result JSONB;
```

`annotation_result` 结构（存储示例）：
```json
{
  "quality": "优质数据",
  "notes": "图像清晰，传感器数据完整"
}
```
`quality` 枚举值：`"优质数据"` | `"可用数据"` | `"问题数据"`
`notes` 可为 `null`。

### 2. 状态机变更

当前 `_TRANSITIONS`：
```python
"rejected": {"assigned"}
```

修改为：
```python
"rejected": {"assigned", "submitted"}
```

原因：标注员完成修改后可直接重新提交，无需工程师先重新分配任务。`annotation_result` 会覆盖写入。

### 3. ORM 模型更新

**`services/task-service/app/models.py`** — `AnnotationTask` 类新增：

```python
from sqlalchemy.dialects.postgresql import JSONB   # 与现有 required_skills 字段保持一致
# ...
annotation_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

### 4. Pydantic Schema 更新

**`TaskOut`** 新增字段（`services/task-service/app/routers/tasks.py`）：

```python
class TaskOut(BaseModel):
    id: str
    project_id: str
    episode_id: str | None
    dataset_version_id: str | None
    type: str
    status: str
    assigned_to: str | None
    guideline_url: str | None
    required_skills: list[str]              # 保留已有字段，勿删
    deadline: str | None
    label_studio_task_id: int | None
    created_by: str | None
    created_at: str
    updated_at: str
    annotation_result: dict | None = None   # ← 新增
```

**`_task_out()` helper** 新增：
```python
"annotation_result": task.annotation_result,
```

### 5. Submit 接口修改

`POST /api/v1/tasks/{task_id}/submit`

**新增 Request body**（`quality` 为必填字符串字面量，使用 Literal 枚举）：

```python
from typing import Literal

class SubmitTaskRequest(BaseModel):
    quality: Literal["优质数据", "可用数据", "问题数据"]   # 必填，FastAPI 自动校验枚举值
    notes: str | None = None
```

- `quality` 必填且值受限，FastAPI 自动返回 422（无需手动 raise）
- 若 body 完全缺失（无 JSON body），FastAPI 也返回 422
- 状态为 `assigned` 或 `rejected` 均适用同一处理
- `annotation_result` 覆盖写入（驳回后重新提交会替换上次记录）

```python
task.annotation_result = {"quality": body.quality, "notes": body.notes}
```

**Response**：返回更新后的 `TaskOut`（含 `annotation_result`）

---

## 前端变更

### 1. api/tasks.ts

**更新 `AnnotationTask` interface**（保留现有所有字段，仅追加 `annotation_result`）：

```typescript
export interface AnnotationTask {
  id: string;
  project_id: string;
  episode_id: string | null;
  dataset_version_id: string | null;
  type: string;
  guideline_url: string | null;
  required_skills: string[];              // 保留
  deadline: string | null;
  status: "created" | "assigned" | "submitted" | "approved" | "rejected";
  assigned_to: string | null;
  label_studio_task_id: number | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  annotation_result: {                    // ← 新增
    quality: "优质数据" | "可用数据" | "问题数据";
    notes: string | null;
  } | null;
}
```

**更新 `useSubmitTask`**（签名从 `taskId: string` 改为对象，注意 `TasksPage.tsx` 中现有调用点已全部移除，无遗留调用）：

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

**新增 `useTask` hook**（与现有 hooks 保持 axios `{ data }` 解构风格）：

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

### 2. TasksPage.tsx — 标注员视图调整

**改动点：**
- `assigned` 任务："查看数据"按钮改为"开始标注"，跳转携带 `task_id`
- `rejected` 任务："重新提交"按钮改为跳转到预览页（携带 `task_id`），**不再直接调用 submit API**
- 移除 `handleSubmit` 函数（提交逻辑统一移至 AnnotationSidebar）

```typescript
// 跳转函数（assigned 和 rejected 均使用）
const handleOpenAnnotation = (task: AnnotationTask) => {
  navigate(`/preview/${task.episode_id}?task_id=${task.id}`)
}
```

按钮文案：
- `assigned`：`开始标注`
- `rejected`：`重新提交`

### 3. PreviewPage.tsx — 条件渲染侧边栏

```typescript
import { useSearchParams } from 'react-router-dom'
import { AnnotationSidebar } from '../components/AnnotationSidebar'

const [searchParams] = useSearchParams()
const taskId = searchParams.get('task_id')
```

**布局变更**（`taskId` 存在时）：

```tsx
<div style={{ display: 'flex', height: '100%' }}>
  {/* 原有视频区域，flex:1 自适应 */}
  <div style={{ flex: 1, minWidth: 0 }}>
    <VideoGrid ... />
    <TimelineControl ... />
  </div>
  {/* 标注侧边栏，固定宽度 */}
  {taskId && (
    <AnnotationSidebar taskId={taskId} />
  )}
</div>
```

无 `task_id` 时不渲染侧边栏，布局不变。

### 4. 新组件 AnnotationSidebar.tsx

**文件**：`web/src/components/AnnotationSidebar.tsx`

**Props**：
```typescript
interface AnnotationSidebarProps {
  taskId: string
}
```

**内部状态**：
- `quality: string | null` — 初始值：`task?.annotation_result?.quality ?? null`
- `notes: string` — 初始值：`task?.annotation_result?.notes ?? ''`

**UI 结构**（从上到下）：
1. 标题区："任务信息"
2. 信息区块（来自 `useTask`）：类型、截止日、当前状态
3. 标注指南链接（若 `guideline_url` 存在）
4. 分隔线
5. "质量评级"标题
6. 三个评级按钮：优质数据 / 可用数据 / 问题数据（互斥，选中高亮）
7. 分隔线
8. "备注（可选）"标签 + `<textarea>`
9. "提交标注"按钮：`quality === null` 时 `disabled`
10. 提示文字："提交后无法修改评级"

**提交逻辑**：
```typescript
import { useNavigate } from 'react-router-dom'
// ...
const navigate = useNavigate()
const { mutate: submitTask, isPending } = useSubmitTask()

const handleSubmit = () => {
  if (!quality) return
  submitTask(
    { taskId, quality, notes: notes || undefined },
    { onSuccess: () => navigate('/tasks') }
  )
}
```

**加载态**：`useTask` loading 时侧边栏显示 skeleton；error 时显示错误提示。

---

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `shared/migrations/versions/004_annotation_tasks_result.py` | 新增 |
| `services/task-service/app/models.py` | 修改：新增 `annotation_result` 字段 |
| `services/task-service/app/routers/tasks.py` | 修改：状态机 + submit body + 校验 + TaskOut + _task_out() |
| `web/src/api/tasks.ts` | 修改：AnnotationTask 类型 + useSubmitTask + 新增 useTask |
| `web/src/pages/TasksPage.tsx` | 修改：按钮文案 + 跳转携带 task_id + 移除 handleSubmit |
| `web/src/pages/PreviewPage.tsx` | 修改：读取 task_id，flex-row 布局，条件渲染侧边栏 |
| `web/src/components/AnnotationSidebar.tsx` | 新增 |

---

## 测试计划

### E2E 测试（`tests/e2e/test_annotation_workflow.py`）

**正常提交流程（API 级别）：**
1. 创建任务 → 分配给标注员 → 标注员提交（带 quality）→ 状态变为 `submitted`
2. `GET /tasks/{id}` 返回 `annotation_result: {quality: "优质数据", notes: "..."}`
3. `GET /tasks/{id}` 返回 `annotation_result: {quality: "可用数据", notes: null}`（无备注场景）

**边界情况（API 级别）：**
4. 提交时不传 quality 字段 → 返回 422
5. 提交时 quality 为非法值（如 "bad"）→ 返回 422
6. 无 body 的 submit 请求 → 返回 422
7. `submitted` 状态任务重复提交 → 返回 409（状态机拒绝）
8. `approved` 状态任务提交 → 返回 409（状态机拒绝）
9. 标注员提交他人任务 → 返回 403

**驳回后重新提交（API 级别）：**
10. 提交 → 工程师驳回 → 状态 `rejected`
11. 标注员从 `rejected` 直接提交（`rejected → submitted`）→ 成功
12. `annotation_result.quality` 更新为新值（覆盖写入）
13. `rejected → assigned` 仍然有效（工程师重新分配不受影响）

**UI 级别（可选，纯 API 已可验证核心逻辑）：**
14. 任务列表"开始标注"按钮 URL 含 `?task_id=`
15. 无 `task_id` 访问 `/preview/{id}` 不显示侧边栏

---

## 不影响的已有功能

- 管理员/工程师任务管理视图（不变）
- MCAP 预览播放、帧加载逻辑（不变）
- Label Studio 集成代码（不变，留待后续）
- 任务审批（approve/reject）接口（不变）
