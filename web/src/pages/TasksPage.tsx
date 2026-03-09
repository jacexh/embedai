import { useState } from "react";
import { useTasks, useAnnotatorsWithWorkload, useAssignTask, type AnnotationTask, type Annotator } from "@/api/tasks";
import { Spinner } from "@/components/Spinner";
import { Pagination } from "@/components/Pagination";

const STATUS_TABS = [
  { value: "pending", label: "待分配" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "rejected", label: "已驳回" },
];

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  in_progress: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待分配",
  in_progress: "进行中",
  completed: "已完成",
  rejected: "已驳回",
};

function AssignModal({
  task,
  annotators,
  onClose,
}: {
  task: AnnotationTask;
  annotators: Annotator[];
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState("");
  const assignTask = useAssignTask();

  const handleConfirm = async () => {
    if (!selectedId) return;
    await assignTask.mutateAsync({ taskId: task.id, assigneeId: selectedId });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-96 p-6">
        <h3 className="text-lg font-semibold mb-4">分配标注任务</h3>
        <p className="text-sm text-gray-600 mb-4">
          Episode: {task.episode?.filename ?? task.episode_id}
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

export function TasksPage() {
  const [activeTab, setActiveTab] = useState("pending");
  const [page, setPage] = useState(1);
  const [assigningTask, setAssigningTask] = useState<AnnotationTask | null>(null);
  const pageSize = 20;

  const { data: tasks, isLoading } = useTasks({ status: activeTab, page, page_size: pageSize });
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
                onClick={() => { setActiveTab(tab.value); setPage(1); }}
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
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-left">
                      <th className="px-4 py-2 font-medium text-gray-600">Episode</th>
                      <th className="px-4 py-2 font-medium text-gray-600">状态</th>
                      <th className="px-4 py-2 font-medium text-gray-600">标注员</th>
                      <th className="px-4 py-2 font-medium text-gray-600">Label Studio</th>
                      <th className="px-4 py-2 font-medium text-gray-600">创建时间</th>
                      <th className="px-4 py-2 font-medium text-gray-600">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {tasks?.items.map((task) => (
                      <tr key={task.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-xs text-gray-700 max-w-xs truncate">
                          {task.episode?.filename ?? task.episode_id}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[task.status]}`}>
                            {STATUS_LABELS[task.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-600">
                          {task.assignee_name ?? <span className="text-gray-400">未分配</span>}
                        </td>
                        <td className="px-4 py-3">
                          {task.label_studio_url ? (
                            <a
                              href={task.label_studio_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline text-xs"
                            >
                              打开 #{task.label_studio_task_id}
                            </a>
                          ) : (
                            <span className="text-gray-400 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {new Date(task.created_at).toLocaleDateString("zh-CN")}
                        </td>
                        <td className="px-4 py-3">
                          {task.status === "pending" && (
                            <button
                              onClick={() => setAssigningTask(task)}
                              className="px-2 py-1 text-xs bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
                            >
                              分配
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {tasks?.items.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                          暂无数据
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pagination
                total={tasks?.total ?? 0}
                page={page}
                pageSize={pageSize}
                onChange={setPage}
              />
            </>
          )}
        </div>

        {/* Annotator workload sidebar (ADR H4) */}
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
                    <span className={`ml-2 text-xs font-medium px-1.5 py-0.5 rounded ${
                      a.pending_task_count > 10 ? "bg-red-100 text-red-700" :
                      a.pending_task_count > 5 ? "bg-yellow-100 text-yellow-700" :
                      "bg-green-100 text-green-700"
                    }`}>
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
