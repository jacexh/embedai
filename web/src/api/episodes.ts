import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { apiClient } from "./client";

export interface Episode {
  id: string;
  project_id: string;
  filename: string;
  format: "mcap" | "hdf5";
  size_bytes: number | null;
  duration_seconds: number | null;
  status: string;
  quality_score: number | null;
  storage_path: string | null;
  recorded_at: string | null;
  ingested_at: string | null;
  created_at: string | null;
  metadata: { thumbnail_url?: string; quality_detail?: Record<string, number> };
}

export interface Topic {
  id: string;
  name: string;
  type: string | null;
  start_time_offset: number | null;
  end_time_offset: number | null;
  message_count: number | null;
  frequency_hz: number | null;
  schema_name: string | null;
}

export interface EpisodeDetail extends Episode {
  topics: Topic[];
}

export interface EpisodeFilters {
  status?: string;
  min_quality?: number;
  format?: string;
  page?: number;
  page_size?: number;
}

export function useEpisodes(filters: EpisodeFilters) {
  return useQuery({
    queryKey: ["episodes", filters],
    queryFn: async () => {
      const { page = 1, page_size = 12, ...rest } = filters;
      const params = new URLSearchParams(
        Object.fromEntries(
          Object.entries({
            ...rest,
            limit: page_size,
            offset: (page - 1) * page_size,
          })
            .filter(([, v]) => v != null && v !== "")
            .map(([k, v]) => [k, String(v)])
        )
      );
      const { data } = await apiClient.get<{ items: Episode[]; total: number }>(
        `/episodes?${params}`
      );
      return data;
    },
  });
}

export function useEpisode(id: string) {
  return useQuery({
    queryKey: ["episodes", id],
    queryFn: async () => {
      const { data } = await apiClient.get<EpisodeDetail>(`/episodes/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useDeleteEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/episodes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["episodes"] }),
  });
}

// ── Upload ────────────────────────────────────────────────────────────────

export interface UploadInitResponse {
  episode_id: string;
  session_id: string;
  chunk_size: number;
  total_chunks: number;
}

async function initUpload(
  filename: string,
  sizeBytes: number,
  format: "mcap" | "hdf5"
): Promise<UploadInitResponse> {
  const { data } = await apiClient.post<UploadInitResponse>(
    "/episodes/upload/init",
    { filename, size_bytes: sizeBytes, format }
  );
  return data;
}

async function uploadChunk(
  sessionId: string,
  chunkIndex: number,
  chunk: Blob
): Promise<void> {
  await apiClient.put(
    `/episodes/upload/${sessionId}/chunk/${chunkIndex}`,
    chunk,
    { headers: { "Content-Type": "application/octet-stream" } }
  );
}

async function completeUpload(sessionId: string): Promise<void> {
  await apiClient.post(`/episodes/upload/${sessionId}/complete`);
}

export interface UploadProgress {
  chunksUploaded: number;
  totalChunks: number;
}

export async function uploadEpisodeFile(
  file: File,
  onProgress: (p: UploadProgress) => void
): Promise<string> {
  const format = file.name.endsWith(".mcap") ? "mcap" : "hdf5";
  const init = await initUpload(file.name, file.size, format);
  const { session_id, chunk_size, total_chunks, episode_id } = init;

  for (let i = 0; i < total_chunks; i++) {
    const start = i * chunk_size;
    const chunk = file.slice(start, start + chunk_size);
    await uploadChunk(session_id, i, chunk);
    onProgress({ chunksUploaded: i + 1, totalChunks: total_chunks });
  }

  await completeUpload(session_id);
  return episode_id;
}

// ── Frame Extraction ──────────────────────────────────────────────────────

export interface FrameOptions {
  topic: string;
  timestamp: number; // nanoseconds
}

export interface FrameResult {
  blobUrl: string;
  timestampNs: number;
}

export async function getFrame(
  episodeId: string,
  options: FrameOptions,
  signal?: AbortSignal
): Promise<FrameResult> {
  const params = new URLSearchParams({
    topic: options.topic,
    timestamp: String(options.timestamp),
  });

  const response = await apiClient.get<ArrayBuffer>(
    `/episodes/${episodeId}/frame?${params}`,
    { responseType: "arraybuffer", signal }
  );

  const timestampNs = parseInt(
    response.headers["x-frame-timestamp"] || String(options.timestamp),
    10
  );

  const blob = new Blob([response.data], { type: "image/jpeg" });
  const blobUrl = URL.createObjectURL(blob);

  return { blobUrl, timestampNs };
}
