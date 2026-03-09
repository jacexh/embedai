import axios from "axios";
import { toast } from "@/store/toast";
import { useAuthStore } from "@/store/auth";

export const apiClient = axios.create({ baseURL: "/api/v1" });

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    } else {
      const detail = err.response?.data?.detail ?? err.response?.data?.error;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join("; ")
          : err.message ?? "请求失败";
      toast.error(message);
    }
    return Promise.reject(err);
  }
);
