import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";

export interface AnnotationTask {
  id: string;
  episode_id: string;
  assignee_id: string | null;
  assignee_name: string | null;
  status: "pending" | "in_progress" | "completed" | "rejected";
  label_studio_task_id: number | null;
  label_studio_url: string | null;
  created_at: string;
  updated_at: string;
  episode?: { filename: string; quality_score: number };
}

export interface Annotator {
  id: string;
  name: string;
  email: string;
  pending_task_count: number;
}

export interface TaskFilters {
  status?: string;
  assignee_id?: string;
  page?: number;
  page_size?: number;
}

export function useTasks(filters: TaskFilters) {
  return useQuery({
    queryKey: ["tasks", filters],
    queryFn: async () => {
      const params = new URLSearchParams(
        Object.fromEntries(
          Object.entries(filters)
            .filter(([, v]) => v != null)
            .map(([k, v]) => [k, String(v)])
        )
      );
      const { data } = await apiClient.get<{ items: AnnotationTask[]; total: number }>(
        `/annotation-tasks?${params}`
      );
      return data;
    },
  });
}

export function useAnnotatorsWithWorkload() {
  return useQuery({
    queryKey: ["annotators", "workload"],
    queryFn: async () => {
      const { data } = await apiClient.get<Annotator[]>("/users?role=annotator&include_workload=true");
      return data;
    },
  });
}

export function useAssignTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, assigneeId }: { taskId: string; assigneeId: string }) =>
      apiClient.put(`/annotation-tasks/${taskId}/assign`, { assignee_id: assigneeId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (episodeId: string) =>
      apiClient.post("/annotation-tasks", { episode_id: episodeId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
