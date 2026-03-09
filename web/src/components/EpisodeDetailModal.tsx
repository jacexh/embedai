import { useEpisode } from "@/api/episodes";
import { Spinner } from "./Spinner";

interface Props {
  episodeId: string;
  onClose: () => void;
}

export function EpisodeDetailModal({ episodeId, onClose }: Props) {
  const { data: episode, isLoading } = useEpisode(episodeId);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 truncate">
            {isLoading ? "加载中…" : episode?.filename}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-4"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-4">
          {isLoading ? (
            <Spinner size="lg" />
          ) : !episode ? (
            <p className="text-gray-400 text-center py-8">加载失败</p>
          ) : (
            <div className="space-y-4">
              {/* Basic info */}
              <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <InfoRow label="格式" value={episode.format.toUpperCase()} />
                <InfoRow label="状态" value={episode.status} />
                <InfoRow
                  label="质量分"
                  value={
                    episode.quality_score != null
                      ? `${Math.round(episode.quality_score * 100)}%`
                      : "—"
                  }
                />
                <InfoRow
                  label="时长"
                  value={
                    episode.duration_seconds != null
                      ? `${Math.floor(episode.duration_seconds / 60)}m ${Math.round(episode.duration_seconds % 60)}s`
                      : "—"
                  }
                />
                <InfoRow
                  label="大小"
                  value={
                    episode.size_bytes != null
                      ? `${(episode.size_bytes / 1024 / 1024).toFixed(1)} MB`
                      : "—"
                  }
                />
                <InfoRow
                  label="录制时间"
                  value={
                    episode.recorded_at
                      ? new Date(episode.recorded_at).toLocaleString("zh-CN")
                      : "—"
                  }
                />
              </div>

              {/* Topics */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">
                  Topics ({episode.topics.length})
                </h3>
                {episode.topics.length === 0 ? (
                  <p className="text-sm text-gray-400">暂无 Topic 数据</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-gray-50 text-gray-600">
                          <th className="text-left px-2 py-1.5 border border-gray-200 font-medium">名称</th>
                          <th className="text-left px-2 py-1.5 border border-gray-200 font-medium">类型</th>
                          <th className="text-right px-2 py-1.5 border border-gray-200 font-medium">消息数</th>
                          <th className="text-right px-2 py-1.5 border border-gray-200 font-medium">频率 (Hz)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {episode.topics.map((t) => (
                          <tr key={t.id} className="hover:bg-gray-50">
                            <td className="px-2 py-1.5 border border-gray-200 font-mono">{t.name}</td>
                            <td className="px-2 py-1.5 border border-gray-200 text-gray-500">{t.type ?? "—"}</td>
                            <td className="px-2 py-1.5 border border-gray-200 text-right">{t.message_count ?? "—"}</td>
                            <td className="px-2 py-1.5 border border-gray-200 text-right">{t.frequency_hz?.toFixed(1) ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-gray-500 shrink-0">{label}:</span>
      <span className="text-gray-900 font-medium">{value}</span>
    </div>
  );
}
