import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";

export interface AnnotationTask {
  id: string;
  project_id: string;
  episode_id: string | null;
  dataset_version_id: string | null;
  type: string;
  guideline_url: string | null;
  required_skills: string[];
  deadline: string | null;
  status: "created" | "assigned" | "submitted" | "approved" | "rejected";
  assigned_to: string | null;
  label_studio_task_id: number | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  annotation_result: {
    quality: "优质数据" | "可用数据" | "问题数据";
    notes: string | null;
  } | null;
}

export interface UserWorkload {
  id: string;
  name: string;
  email: string;
  role: string;
  skill_tags: string[];
  pending_task_count: number;
}

export interface TaskFilters {
  status?: string;
  assigned_to?: string;
}

export function useTasks(filters: TaskFilters = {}) {
  return useQuery({
    queryKey: ["tasks", filters],
    queryFn: async () => {
      const params = new URLSearchParams(
        Object.fromEntries(
          Object.entries(filters)
            .filter(([, v]) => v != null && v !== "")
            .map(([k, v]) => [k, String(v)])
        )
      );
      const { data } = await apiClient.get<AnnotationTask[]>(`/tasks?${params}`);
      return data;
    },
  });
}

export function useAnnotatorsWithWorkload() {
  return useQuery({
    queryKey: ["users", "workload"],
    queryFn: async () => {
      const { data } = await apiClient.get<UserWorkload[]>(
        "/users?role=annotator&include_workload=true"
      );
      return data;
    },
  });
}

export function useAssignTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, userId }: { taskId: string; userId: string }) =>
      apiClient.post(`/tasks/${taskId}/assign`, { user_id: userId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (episodeId: string) =>
      apiClient.post<AnnotationTask>("/tasks", {
        episode_id: episodeId,
        type: "video_annotation",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

interface SubmitTaskPayload {
  taskId: string;
  quality: string;
  notes?: string;
}

export function useSubmitTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, quality, notes }: SubmitTaskPayload) =>
      apiClient.post(`/tasks/${taskId}/submit`, { quality, notes }),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["task", taskId] });
    },
  });
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: async () => {
      const { data } = await apiClient.get<AnnotationTask>(`/tasks/${taskId}`);
      return data;
    },
    enabled: !!taskId,
  });
}

export function useApproveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => apiClient.post(`/tasks/${taskId}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useRejectTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, comment }: { taskId: string; comment?: string }) =>
      apiClient.post(`/tasks/${taskId}/reject`, { comment }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
