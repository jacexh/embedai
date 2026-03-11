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

type QualityValue = (typeof QUALITY_OPTIONS)[number]["value"];

const IDLE_BTN = "border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:bg-gray-50";

export function AnnotationSidebar({ taskId }: AnnotationSidebarProps) {
  const navigate = useNavigate();
  const { data: task, isLoading, isError } = useTask(taskId);
  const { mutate: submitTask, isPending } = useSubmitTask();

  const [quality, setQuality] = useState<QualityValue | null>(null);
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
