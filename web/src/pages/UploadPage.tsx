import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { uploadEpisodeFile } from "@/api/episodes";
import type { UploadProgress } from "@/api/episodes";

type UploadState = "idle" | "uploading" | "done" | "error";

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const f = files[0];
    if (!f.name.endsWith(".mcap") && !f.name.endsWith(".h5") && !f.name.endsWith(".hdf5")) {
      setErrorMsg("仅支持 .mcap 或 .hdf5 / .h5 文件");
      return;
    }
    setErrorMsg("");
    setFile(f);
    setState("idle");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!file) return;
    setState("uploading");
    setProgress(null);
    setErrorMsg("");
    try {
      await uploadEpisodeFile(file, (p) => setProgress(p));
      await qc.invalidateQueries({ queryKey: ["episodes"] });
      setState("done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "上传失败，请重试";
      setErrorMsg(msg);
      setState("error");
    }
  };

  const percent =
    progress && progress.totalChunks > 0
      ? Math.round((progress.chunksUploaded / progress.totalChunks) * 100)
      : 0;

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">上传数据录制文件</h1>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
          isDragging
            ? "border-blue-400 bg-blue-50"
            : file
            ? "border-green-400 bg-green-50"
            : "border-gray-300 bg-gray-50 hover:border-gray-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mcap,.h5,.hdf5"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {file ? (
          <div>
            <p className="text-lg font-medium text-gray-800">{file.name}</p>
            <p className="text-sm text-gray-500 mt-1">
              {(file.size / 1024 / 1024).toFixed(1)} MB &middot;{" "}
              {file.name.endsWith(".mcap") ? "MCAP" : "HDF5"}
            </p>
            <p className="text-xs text-gray-400 mt-2">点击或拖入新文件以替换</p>
          </div>
        ) : (
          <div>
            <p className="text-gray-500">拖入文件或点击选择</p>
            <p className="text-xs text-gray-400 mt-1">支持 .mcap、.hdf5、.h5</p>
          </div>
        )}
      </div>

      {/* Progress */}
      {state === "uploading" && (
        <div className="mt-6">
          <div className="flex justify-between text-sm text-gray-600 mb-1">
            <span>上传中…</span>
            <span>{percent}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-200"
              style={{ width: `${percent}%` }}
            />
          </div>
          {progress && (
            <p className="text-xs text-gray-400 mt-1">
              {progress.chunksUploaded} / {progress.totalChunks} 块
            </p>
          )}
        </div>
      )}

      {/* Success */}
      {state === "done" && (
        <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-green-700 font-medium">上传成功！文件正在后台处理中。</p>
          <p className="text-sm text-green-600 mt-1">
            处理完成后可在"数据录制"页面查看。
          </p>
          <div className="mt-3 flex gap-3">
            <button
              onClick={() => navigate("/episodes")}
              className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
            >
              查看数据录制
            </button>
            <button
              onClick={() => { setFile(null); setState("idle"); setProgress(null); }}
              className="px-4 py-2 bg-white text-gray-600 text-sm rounded border border-gray-300 hover:bg-gray-50"
            >
              继续上传
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {errorMsg && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
          {errorMsg}
        </div>
      )}

      {/* Upload Button */}
      {file && state !== "uploading" && state !== "done" && (
        <button
          onClick={handleUpload}
          className="mt-6 w-full py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          开始上传
        </button>
      )}
    </div>
  );
}
