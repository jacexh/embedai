import type { Episode } from "@/api/episodes";
import { QualityBadge } from "./QualityBadge";

interface EpisodeCardProps {
  episode: Episode;
  onCreateTask?: (episodeId: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  uploading: "上传中",
  processing: "处理中",
  ready: "就绪",
  failed: "失败",
  low_quality: "低质量",
  quarantined: "隔离",
};

const STATUS_COLORS: Record<string, string> = {
  ready: "text-green-600",
  failed: "text-red-600",
  low_quality: "text-yellow-600",
  quarantined: "text-red-800",
  processing: "text-blue-600",
  uploading: "text-gray-500",
};

export function EpisodeCard({ episode, onCreateTask }: EpisodeCardProps) {
  const duration = episode.duration_seconds
    ? `${Math.floor(episode.duration_seconds / 60)}m ${Math.round(episode.duration_seconds % 60)}s`
    : "—";

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow p-4">
      {episode.metadata.thumbnail_url ? (
        <img
          src={episode.metadata.thumbnail_url}
          alt={episode.filename}
          className="w-full h-32 object-cover rounded mb-3 bg-gray-100"
        />
      ) : (
        <div className="w-full h-32 bg-gray-100 rounded mb-3 flex items-center justify-center text-gray-400 text-sm">
          {episode.format.toUpperCase()}
        </div>
      )}

      <div className="space-y-1">
        <p className="text-sm font-medium text-gray-900 truncate" title={episode.filename}>
          {episode.filename}
        </p>
        <div className="flex items-center justify-between">
          <span className={`text-xs font-medium ${STATUS_COLORS[episode.status] ?? "text-gray-500"}`}>
            {STATUS_LABELS[episode.status] ?? episode.status}
          </span>
          <QualityBadge score={episode.quality_score} />
        </div>
        <p className="text-xs text-gray-500">时长: {duration}</p>
        <p className="text-xs text-gray-400">
          {new Date(episode.recorded_at).toLocaleString("zh-CN")}
        </p>
      </div>

      {episode.status === "ready" && onCreateTask && (
        <button
          onClick={() => onCreateTask(episode.id)}
          className="mt-3 w-full px-3 py-1.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors"
        >
          创建标注任务
        </button>
      )}
    </div>
  );
}
