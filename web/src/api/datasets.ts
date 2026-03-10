import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";

export interface Dataset {
  id: string;
  name: string;
  description: string;
  project_id: string;
  version_count: number;
  created_at: string;
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_tag: string;
  episode_count: number;
  size_estimate_bytes: number;
  is_immutable: boolean;
  created_at: string;
}

export interface ExportJob {
  id: string;
  version_id: string;
  format: "webdataset" | "raw" | "huggingface";
  status: "pending" | "running" | "completed" | "failed";
  target_bucket: string;
  manifest_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export function useDatasets() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ items: Dataset[]; total: number }>("/datasets");
      return data;
    },
  });
}

export function useDatasetVersions(datasetId: string) {
  return useQuery({
    queryKey: ["datasets", datasetId, "versions"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ items: DatasetVersion[] }>(
        `/datasets/${datasetId}/versions`
      );
      return data;
    },
    enabled: !!datasetId,
  });
}

export function useCreateDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description: string }) =>
      apiClient.post<Dataset>("/datasets", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });
}

export function useCreateVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      datasetId,
      payload,
    }: {
      datasetId: string;
      payload: { episode_ids: string[]; version_tag: string; filter?: Record<string, unknown> };
    }) => {
      // Backend expects episode_refs: [{episode_id}], not episode_ids: [string]
      const { episode_ids, version_tag } = payload;
      return apiClient.post<DatasetVersion>(`/datasets/${datasetId}/versions`, {
        version_tag,
        episode_refs: episode_ids.map((id) => ({ episode_id: id })),
      });
    },
    onSuccess: (_, { datasetId }) =>
      qc.invalidateQueries({ queryKey: ["datasets", datasetId, "versions"] }),
  });
}

export function useExportJobs(versionId?: string) {
  return useQuery({
    queryKey: ["export-jobs", versionId],
    queryFn: async () => {
      const url = versionId ? `/export-jobs?version_id=${versionId}` : "/export-jobs";
      const { data } = await apiClient.get<{ items: ExportJob[] }>(url);
      return data;
    },
  });
}

export function useExportJob(jobId: string) {
  return useQuery({
    queryKey: ["export-jobs", jobId],
    queryFn: async () => {
      const { data } = await apiClient.get<ExportJob>(`/export-jobs/${jobId}`);
      return data;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 3000 : false;
    },
    enabled: !!jobId,
  });
}

export function useCreateExportJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { version_id: string; format: string; target_bucket: string }) =>
      apiClient.post<ExportJob>("/export-jobs", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["export-jobs"] }),
  });
}
