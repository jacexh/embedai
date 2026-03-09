import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useDatasets,
  useDatasetVersions,
  useCreateDataset,
  type Dataset,
} from "@/api/datasets";
import { Spinner } from "@/components/Spinner";

function CreateDatasetModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const createDataset = useCreateDataset();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createDataset.mutateAsync({ name, description });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-96 p-6">
        <h3 className="text-lg font-semibold mb-4">创建数据集</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="robot-navigation-v1"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm resize-none"
              placeholder="数据集描述..."
            />
          </div>
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!name || createDataset.isPending}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {createDataset.isPending ? "创建中..." : "创建"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DatasetCard({ dataset }: { dataset: Dataset }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const { data: versions, isLoading } = useDatasetVersions(expanded ? dataset.id : "");

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div>
          <h3 className="font-semibold text-gray-900">{dataset.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{dataset.description}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{dataset.version_count} 个版本</span>
          <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 p-4">
          {isLoading ? (
            <Spinner size="sm" />
          ) : versions?.items.length === 0 ? (
            <p className="text-sm text-gray-400">暂无版本，请先创建</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs">
                  <th className="pb-2">版本标签</th>
                  <th className="pb-2">Episode 数</th>
                  <th className="pb-2">大小估算</th>
                  <th className="pb-2">创建时间</th>
                  <th className="pb-2">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {versions?.items.map((v) => (
                  <tr key={v.id}>
                    <td className="py-2 font-mono text-xs">{v.version_tag}</td>
                    <td className="py-2">{v.episode_count}</td>
                    <td className="py-2 text-xs text-gray-500">
                      {v.size_estimate_bytes
                        ? `${(v.size_estimate_bytes / 1024 ** 3).toFixed(1)} GB`
                        : "—"}
                    </td>
                    <td className="py-2 text-xs text-gray-500">
                      {new Date(v.created_at).toLocaleDateString("zh-CN")}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => navigate(`/export?version_id=${v.id}`)}
                        className="px-2 py-0.5 text-xs bg-green-50 text-green-700 rounded hover:bg-green-100"
                      >
                        导出
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button
            onClick={() => navigate(`/datasets/${dataset.id}/new-version`)}
            className="mt-3 px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            + 创建新版本
          </button>
        </div>
      )}
    </div>
  );
}

export function DatasetsPage() {
  const [showCreate, setShowCreate] = useState(false);
  const { data, isLoading } = useDatasets();

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">数据集管理</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
        >
          + 新建数据集
        </button>
      </div>

      {isLoading ? (
        <Spinner size="lg" />
      ) : (
        <div className="space-y-3">
          {data?.items.map((ds) => (
            <DatasetCard key={ds.id} dataset={ds} />
          ))}
          {data?.items.length === 0 && (
            <div className="text-center text-gray-400 py-12">暂无数据集，请创建一个</div>
          )}
        </div>
      )}

      {showCreate && <CreateDatasetModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}
