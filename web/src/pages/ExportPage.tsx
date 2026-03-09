import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useCreateExportJob, useExportJob, useExportJobs, type ExportJob } from "@/api/datasets";
import { Spinner } from "@/components/Spinner";

const FORMAT_OPTIONS = [
  { value: "webdataset", label: "WebDataset (推荐, ADR H6)", desc: "200-500MB/shard，适合大规模训练" },
  { value: "raw", label: "裸文件 + JSON sidecar", desc: "原始格式，灵活性高" },
  { value: "huggingface", label: "HuggingFace Parquet", desc: "HDF5 场景，P1 支持" },
];

const STATUS_COLORS: Record<string, string> = {
  pending: "text-gray-500",
  running: "text-blue-600",
  completed: "text-green-600",
  failed: "text-red-600",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  running: "导出中",
  completed: "已完成",
  failed: "失败",
};

function ExportJobRow({ job }: { job: ExportJob }) {
  // Poll status if running
  const { data: live } = useExportJob(
    job.status === "running" || job.status === "pending" ? job.id : ""
  );
  const display = live ?? job;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 font-mono text-xs text-gray-600">{display.id.slice(0, 8)}…</td>
      <td className="px-4 py-3 text-sm">{display.format}</td>
      <td className="px-4 py-3 text-sm">{display.target_bucket}</td>
      <td className={`px-4 py-3 text-sm font-medium ${STATUS_COLORS[display.status]}`}>
        {STATUS_LABELS[display.status]}
        {display.status === "running" && (
          <span className="ml-1 inline-block animate-spin">⟳</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm">
        {display.manifest_url ? (
          <a
            href={display.manifest_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline text-xs"
          >
            下载 manifest
          </a>
        ) : display.error_message ? (
          <span className="text-red-500 text-xs">{display.error_message}</span>
        ) : (
          <span className="text-gray-400 text-xs">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">
        {new Date(display.created_at).toLocaleString("zh-CN")}
      </td>
    </tr>
  );
}

function NewExportForm({ versionId }: { versionId: string }) {
  const [format, setFormat] = useState("webdataset");
  const [bucket, setBucket] = useState("");
  const createJob = useCreateExportJob();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createJob.mutateAsync({ version_id: versionId, format, target_bucket: bucket });
    setBucket("");
  };

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 mb-6">
      <h3 className="font-semibold text-blue-900 mb-3">创建导出任务</h3>
      <p className="text-xs text-blue-700 mb-4">版本 ID: <span className="font-mono">{versionId}</span></p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">导出格式</label>
          <div className="space-y-2">
            {FORMAT_OPTIONS.map((opt) => (
              <label key={opt.value} className="flex items-start gap-3 cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value={opt.value}
                  checked={format === opt.value}
                  onChange={() => setFormat(opt.value)}
                  className="mt-0.5"
                />
                <div>
                  <span className="text-sm font-medium text-gray-800">{opt.label}</span>
                  <p className="text-xs text-gray-500">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            目标 S3 Bucket
          </label>
          <input
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
            required
            placeholder="s3://my-bucket/exports/"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={!bucket || createJob.isPending}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {createJob.isPending ? "提交中..." : "开始导出"}
        </button>
      </form>
    </div>
  );
}

export function ExportPage() {
  const [searchParams] = useSearchParams();
  const versionId = searchParams.get("version_id") ?? "";
  const { data, isLoading } = useExportJobs(versionId || undefined);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">导出管理</h1>

      {versionId && <NewExportForm versionId={versionId} />}

      <div className="bg-white border border-gray-200 rounded-lg">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">导出历史</h2>
        </div>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left text-xs text-gray-500">
                  <th className="px-4 py-2">任务 ID</th>
                  <th className="px-4 py-2">格式</th>
                  <th className="px-4 py-2">目标 Bucket</th>
                  <th className="px-4 py-2">状态</th>
                  <th className="px-4 py-2">结果</th>
                  <th className="px-4 py-2">创建时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data?.items.map((job) => (
                  <ExportJobRow key={job.id} job={job} />
                ))}
                {data?.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      暂无导出任务
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
