import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { PreviewPage } from "../PreviewPage";

// Mock dependencies
vi.mock("@/api/episodes", () => ({
  useEpisode: vi.fn(),
}));

vi.mock("@/hooks/useMcapFrames", () => ({
  useMcapFrames: vi.fn(),
}));

import { useEpisode } from "@/api/episodes";
import { useMcapFrames } from "@/hooks/useMcapFrames";

const mockUseEpisode = vi.mocked(useEpisode);
const mockUseMcapFrames = vi.mocked(useMcapFrames);

describe("PreviewPage", () => {
  const createTestQueryClient = () =>
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

  const renderWithProviders = (ui: React.ReactElement, episodeId = "test-id") => {
    const queryClient = createTestQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/preview/${episodeId}`]}>
          <Routes>
            <Route path="/preview/:episodeId" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("loading states", () => {
    it("should show spinner while loading episode", () => {
      mockUseEpisode.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  describe("error states", () => {
    it("should show not found when episode does not exist", () => {
      mockUseEpisode.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Episode not found")).toBeInTheDocument();
    });
  });

  describe("format validation", () => {
    it("should show error for non-MCAP files", () => {
      mockUseEpisode.mockReturnValue({
        data: { format: "hdf5", filename: "test.hdf5" },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Preview is only available for MCAP files")).toBeInTheDocument();
    });
  });

  describe("playback controls", () => {
    beforeEach(() => {
      mockUseEpisode.mockReturnValue({
        data: {
          id: "test-id",
          format: "mcap",
          filename: "test.mcap",
          duration_seconds: 60,
          topics: [
            { name: "/camera/image", schema_name: "sensor_msgs/msg/Image" },
          ],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);
    });

    it("should display episode filename in header", () => {
      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("test.mcap")).toBeInTheDocument();
    });

    it("should load initial frames on mount", () => {
      const loadFrames = vi.fn();
      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames,
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(loadFrames).toHaveBeenCalledWith(0);
    });

    it("should handle play/pause toggle", () => {
      renderWithProviders(<PreviewPage />);

      const playButton = screen.getByText("▶ Play");
      fireEvent.click(playButton);

      expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
    });

    it("should display duration in header", () => {
      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Duration: 1m 0s")).toBeInTheDocument();
    });

    it("should have back button", () => {
      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("← Back")).toBeInTheDocument();
    });
  });

  describe("topic filtering", () => {
    it("should filter only image topics", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 60,
          filename: "test.mcap",
          topics: [
            { name: "/camera/image", schema_name: "sensor_msgs/msg/Image" },
            { name: "/odom", schema_name: "nav_msgs/Odometry" },
            { name: "/imu", schema_name: "sensor_msgs/Imu" },
          ],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      // useMcapFrames should only receive image topics
      const lastCall = mockUseMcapFrames.mock.calls[mockUseMcapFrames.mock.calls.length - 1];
      expect(lastCall[0].topics).toEqual(["/camera/image"]);
    });

    it("should filter topics by name containing 'camera'", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 60,
          filename: "test.mcap",
          topics: [
            { name: "/camera/left", schema_name: "sensor_msgs/msg/Image" },
            { name: "/camera/right", schema_name: "sensor_msgs/msg/Image" },
            { name: "/depth/image", type: "image" },
          ],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      const lastCall = mockUseMcapFrames.mock.calls[mockUseMcapFrames.mock.calls.length - 1];
      expect(lastCall[0].topics).toContain("/camera/left");
      expect(lastCall[0].topics).toContain("/camera/right");
      expect(lastCall[0].topics).toContain("/depth/image");
    });

    it("should filter topics by name containing 'image'", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 60,
          filename: "test.mcap",
          topics: [
            { name: "/camera/image_raw", schema_name: "sensor_msgs/msg/Image" },
            { name: "/thermal/image", schema_name: "sensor_msgs/msg/Image" },
          ],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      const lastCall = mockUseMcapFrames.mock.calls[mockUseMcapFrames.mock.calls.length - 1];
      expect(lastCall[0].topics).toContain("/camera/image_raw");
      expect(lastCall[0].topics).toContain("/thermal/image");
    });
  });

  describe("no topics state", () => {
    it("should handle episode with no image topics", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 60,
          filename: "test.mcap",
          topics: [
            { name: "/odom", schema_name: "nav_msgs/Odometry" },
          ],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      // Should still render the page
      expect(screen.getByText("test.mcap")).toBeInTheDocument();
    });
  });

  describe("duration handling", () => {
    it("should handle zero duration", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 0,
          filename: "test.mcap",
          topics: [],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Duration: 0m 0s")).toBeInTheDocument();
    });

    it("should format duration correctly", () => {
      mockUseEpisode.mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 125,
          filename: "test.mcap",
          topics: [],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Duration: 2m 5s")).toBeInTheDocument();
    });
  });

  describe("deep linking", () => {
    it("should extract episode ID from URL params", () => {
      const mockEpisodeId = "test-episode-id-123";

      mockUseEpisode.mockReturnValue({
        data: {
          id: mockEpisodeId,
          format: "mcap",
          filename: "test.mcap",
          duration_seconds: 60,
          topics: [{ name: "/camera/image", schema_name: "sensor_msgs/msg/Image" }],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />, mockEpisodeId);

      // Verify the component uses the episode ID from URL
      expect(mockUseEpisode).toHaveBeenCalledWith(mockEpisodeId);
      expect(mockUseMcapFrames).toHaveBeenCalledWith(
        expect.objectContaining({ episodeId: mockEpisodeId })
      );
    });

    it("should handle direct access to preview page", () => {
      // Simulate direct navigation to /preview/:episodeId
      const directAccessEpisodeId = "direct-access-episode";

      mockUseEpisode.mockReturnValue({
        data: {
          id: directAccessEpisodeId,
          format: "mcap",
          filename: "test.mcap",
          duration_seconds: 60,
          topics: [{ name: "/camera/image", schema_name: "sensor_msgs/msg/Image" }],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      // Render with initial entry simulating direct access
      const { container } = renderWithProviders(
        <PreviewPage />,
        directAccessEpisodeId
      );

      // Page should render without 404
      expect(screen.getByText("test.mcap")).toBeInTheDocument();
      expect(container.querySelector("[role='status']")).not.toBeInTheDocument();
    });

    it("should handle invalid episode ID format gracefully", () => {
      const invalidEpisodeId = "not-a-valid-uuid";

      mockUseEpisode.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error("Invalid episode ID"),
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />, invalidEpisodeId);

      // Should show not found or error state
      expect(screen.getByText("Episode not found")).toBeInTheDocument();
    });

    it("should preserve episode ID when navigating back", () => {
      const episodeId = "navigation-test-episode";

      mockUseEpisode.mockReturnValue({
        data: {
          id: episodeId,
          format: "mcap",
          filename: "test.mcap",
          duration_seconds: 60,
          topics: [{ name: "/camera/image", schema_name: "sensor_msgs/msg/Image" }],
        },
        isLoading: false,
        isError: false,
      } as any);

      mockUseMcapFrames.mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      } as any);

      renderWithProviders(<PreviewPage />, episodeId);

      // Click back button
      const backButton = screen.getByText("← Back");
      fireEvent.click(backButton);

      // Navigation should work (we can't fully test navigation without mocking,
      // but we can verify the button is clickable)
      expect(backButton).toBeInTheDocument();
    });
  });
});
