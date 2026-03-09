import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";

export interface Episode {
  id: string;
  filename: string;
  format: "mcap" | "hdf5";
  duration_seconds: number;
  quality_score: number;
  status: string;
  metadata: { thumbnail_url?: string; quality_detail?: Record<string, number> };
  recorded_at: string;
  project_id: string;
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
      const params = new URLSearchParams(
        Object.fromEntries(
          Object.entries(filters)
            .filter(([, v]) => v != null)
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
      const { data } = await apiClient.get<Episode>(`/episodes/${id}`);
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
