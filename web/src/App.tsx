import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { EpisodesPage } from "@/pages/EpisodesPage";
import { TasksPage } from "@/pages/TasksPage";
import { DatasetsPage } from "@/pages/DatasetsPage";
import { ExportPage } from "@/pages/ExportPage";
import { UploadPage } from "@/pages/UploadPage";
import { PreviewPage } from "@/pages/PreviewPage";
import { ToastContainer } from "@/components/ToastContainer";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastContainer />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/episodes" replace />} />
            <Route path="episodes" element={<EpisodesPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="datasets" element={<DatasetsPage />} />
            <Route path="export" element={<ExportPage />} />
            <Route path="preview/:episodeId" element={<PreviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
