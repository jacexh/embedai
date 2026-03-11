import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useTasks,
  useAnnotatorsWithWorkload,
  useAssignTask,
  type AnnotationTask,
  type UserWorkload,
} from "@/api/tasks";
import { Spinner } from "@/components/Spinner";
import { toast } from "@/store/toast";
import { useAuthStore } from "@/store/auth";

// Backend status values (ADR H4)
const STATUS_TABS = [
  { value: "created", label: "待分配" },
  { value: "assigned", label: "进行中" },
  { value: "submitted", label: "待审批" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已驳回" },
];

const ANNOTATOR_STATUS_TABS = [
  { value: "assigned", label: "进行中" },
  { value: "submitted", label: "已提交" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已驳回" },
];

const STATUS_COLORS: Record<string, string> = {
  created: "bg-gray-100 text-gray-700",
  assigned: "bg-blue-100 text-blue-700",
  submitted: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  created: "待分配",
  assigned: "进行中",
  submitted: "待审批",
  approved: "已通过",
  rejected: "已驳回",
};

function AssignModal({
  task,
  annotators,
  onClose,
}: {
  task: AnnotationTask;
  annotators: UserWorkload[];
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState("");
  const assignTask = useAssignTask();

  const handleConfirm = async () => {
    if (!selectedId) return;
    try {
      await assignTask.mutateAsync({ taskId: task.id, userId: selectedId });
      toast.success("任务已分配");
      onClose();
    } catch {
      // error toast shown by apiClient interceptor
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-96 p-6">
        <h3 className="text-lg font-semibold mb-4">分配标注任务</h3>
        <p className="text-sm text-gray-600 mb-4">
          Episode ID: <span className="font-mono text-xs">{task.episode_id ?? "—"}</span>
        </p>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm mb-4"
        >
          <option value="">选择标注员...</option>
          {annotators.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} — {a.pending_task_count} 待办
            </option>
          ))}
        </select>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedId || assignTask.isPending}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {assignTask.isPending ? "分配中..." : "确认分配"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Annotator view: shows tasks assigned to current user with submit action
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Engineer/Admin view: task management with assignment
// ---------------------------------------------------------------------------

function ManagementTasksView() {
  const [activeTab, setActiveTab] = useState("created");
  const [assigningTask, setAssigningTask] = useState<AnnotationTask | null>(null);

  const { data: tasks = [], isLoading } = useTasks({ status: activeTab });
  const { data: annotators = [] } = useAnnotatorsWithWorkload();

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">标注任务管理</h1>

      <div className="flex gap-6">
        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Tabs */}
          <div className="flex border-b border-gray-200 mb-4">
            {STATUS_TABS.map((tab) => (
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

          {/* Task Table */}
          {isLoading ? (
            <Spinner />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left">
                    <th className="px-4 py-2 font-medium text-gray-600">Episode ID</th>
                    <th className="px-4 py-2 font-medium text-gray-600">类型</th>
                    <th className="px-4 py-2 font-medium text-gray-600">状态</th>
                    <th className="px-4 py-2 font-medium text-gray-600">标注员</th>
                    <th className="px-4 py-2 font-medium text-gray-600">创建时间</th>
                    <th className="px-4 py-2 font-medium text-gray-600">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {tasks.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                        暂无数据
                      </td>
                    </tr>
                  ) : (
                    tasks.map((task) => (
                      <tr key={task.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-xs text-gray-700 max-w-xs truncate">
                          {task.episode_id ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{task.type}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[task.status] ?? "bg-gray-100 text-gray-600"}`}>
                            {STATUS_LABELS[task.status] ?? task.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {task.assigned_to ? (
                            <span className="font-mono">{task.assigned_to.slice(0, 8)}…</span>
                          ) : (
                            <span className="text-gray-400">未分配</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {task.created_at
                            ? new Date(task.created_at).toLocaleDateString("zh-CN")
                            : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {task.status === "created" && (
                            <button
                              onClick={() => setAssigningTask(task)}
                              className="px-2 py-1 text-xs bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
                            >
                              分配
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Annotator workload sidebar */}
        <aside className="w-64 shrink-0">
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-3">标注员负载</h3>
            {annotators.length === 0 ? (
              <p className="text-sm text-gray-400">暂无数据</p>
            ) : (
              <ul className="space-y-2">
                {annotators.map((a) => (
                  <li key={a.id} className="flex justify-between items-center text-sm">
                    <span className="text-gray-700 truncate">{a.name}</span>
                    <span
                      className={`ml-2 text-xs font-medium px-1.5 py-0.5 rounded ${
                        a.pending_task_count > 10
                          ? "bg-red-100 text-red-700"
                          : a.pending_task_count > 5
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-green-100 text-green-700"
                      }`}
                    >
                      {a.pending_task_count} 待办
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>

      {assigningTask && (
        <AssignModal
          task={assigningTask}
          annotators={annotators}
          onClose={() => setAssigningTask(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Entry point: route to appropriate view based on role
// ---------------------------------------------------------------------------

export function TasksPage() {
  const user = useAuthStore((s) => s.user);
  const isAnnotator = user?.role?.startsWith("annotator") ?? false;

  if (isAnnotator && user) {
    return <AnnotatorTasksView userId={user.id} />;
  }

  return <ManagementTasksView />;
}
