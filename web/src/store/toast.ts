import { create } from "zustand";

export interface ToastItem {
  id: string;
  message: string;
  type: "error" | "success" | "info";
}

interface ToastStore {
  toasts: ToastItem[];
  add: (message: string, type?: ToastItem["type"]) => void;
  remove: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  add: (message, type = "info") => {
    const id = `${Date.now()}-${Math.random()}`;
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

// Call outside React components (e.g. from apiClient interceptor)
export const toast = {
  error: (message: string) => useToastStore.getState().add(message, "error"),
  success: (message: string) => useToastStore.getState().add(message, "success"),
  info: (message: string) => useToastStore.getState().add(message, "info"),
};
