import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEpisodes, useDeleteEpisode } from "@/api/episodes";
import { useCreateTask } from "@/api/tasks";
import { EpisodeCard } from "@/components/EpisodeCard";
import { EpisodeDetailModal } from "@/components/EpisodeDetailModal";
import { Spinner } from "@/components/Spinner";
import { Pagination } from "@/components/Pagination";
import { toast } from "@/store/toast";
import { useAuthStore } from "@/store/auth";

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "ready", label: "就绪" },
  { value: "processing", label: "处理中" },
  { value: "low_quality", label: "低质量" },
  { value: "failed", label: "失败" },
];

const FORMAT_OPTIONS = [
  { value: "", label: "全部格式" },
  { value: "mcap", label: "MCAP" },
  { value: "hdf5", label: "HDF5" },
];

export function EpisodesPage() {
  const [status, setStatus] = useState("");
  const [format, setFormat] = useState("");
  const [minQuality, setMinQuality] = useState(0);
  const [page, setPage] = useState(1);
  const [detailId, setDetailId] = useState<string | null>(null);
  const pageSize = 12;

  const { data, isLoading, isError } = useEpisodes({
    status: status || undefined,
    format: format || undefined,
    min_quality: minQuality || undefined,
    page,
    page_size: pageSize,
  });

  const createTask = useCreateTask();
  const deleteEpisode = useDeleteEpisode();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const hasActiveFilter = !!(status || format || minQuality);

  const handleCreateTask = async (episodeId: string) => {
    try {
      await createTask.mutateAsync(episodeId);
      toast.success("标注任务已创建");
    } catch {
      // error toast shown by apiClient interceptor
    }
  };

  const handleDelete = async (episodeId: string) => {
    try {
      await deleteEpisode.mutateAsync(episodeId);
      toast.success("已删除");
    } catch {
      // error toast shown by apiClient interceptor
    }
  };

  const handlePreview = (episodeId: string) => {
    navigate(`/preview/${episodeId}`);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">数据录制 / Episodes</h1>
        <span className="text-sm text-gray-500">共 {data?.total ?? 0} 条</span>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3 mb-6 bg-gray-50 p-4 rounded-lg">
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={format}
          onChange={(e) => { setFormat(e.target.value); setPage(1); }}
          className="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white"
        >
          {FORMAT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">最低质量:</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={minQuality}
            onChange={(e) => { setMinQuality(parseFloat(e.target.value)); setPage(1); }}
            className="w-24"
          />
          <span className="text-sm text-gray-700 w-8">{Math.round(minQuality * 100)}%</span>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <Spinner size="lg" />
      ) : isError ? (
        <div className="text-center text-red-500 py-12">加载失败，请刷新重试</div>
      ) : data?.items.length === 0 ? (
        <div className="text-center text-gray-400 py-12">
          <p className="text-lg mb-2">暂无数据</p>
          {hasActiveFilter ? (
            <p className="text-sm">
              当前有过滤条件，请尝试{" "}
              <button
                onClick={() => { setStatus(""); setFormat(""); setMinQuality(0); setPage(1); }}
                className="text-blue-600 hover:underline"
              >
                清除过滤
              </button>
            </p>
          ) : (
            <p className="text-sm">
              请先{" "}
              <a href="/upload" className="text-blue-600 hover:underline">上传录制文件</a>
              ，或检查当前账号（
              <span className="font-mono text-xs text-gray-500">{user?.email}</span>
              ）是否正确
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {data?.items.map((ep) => (
              <EpisodeCard
                key={ep.id}
                episode={ep}
                onCreateTask={handleCreateTask}
                onDelete={handleDelete}
                onDetail={setDetailId}
                onPreview={handlePreview}
              />
            ))}
          </div>
          <Pagination
            total={data?.total ?? 0}
            page={page}
            pageSize={pageSize}
            onChange={setPage}
          />
        </>
      )}

      {/* Detail Modal */}
      {detailId && (
        <EpisodeDetailModal
          episodeId={detailId}
          onClose={() => setDetailId(null)}
        />
      )}
    </div>
  );
}
