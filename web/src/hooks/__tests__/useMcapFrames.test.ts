import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useMcapFrames } from "../useMcapFrames";
import * as episodesApi from "@/api/episodes";

// Mock API
vi.mock("@/api/episodes");

describe("useMcapFrames", () => {
  const mockGetFrame = vi.mocked(episodesApi.getFrame);

  beforeEach(() => {
    vi.clearAllMocks();
    // @ts-ignore
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("initialization", () => {
    it("should initialize with empty frames and not loading", () => {
      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "test-episode", topics: [] })
      );

      expect(result.current.frames.size).toBe(0);
      expect(result.current.isLoading).toBe(false);
    });

    it("should initialize with empty frames when topics provided", () => {
      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      expect(result.current.frames.size).toBe(0);
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe("loadFrames", () => {
    it("should load frames for all topics", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(result.current.frames.size).toBe(2);
      expect(result.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(result.current.frames.get("/camera/image2")).toBe("blob:test-1");
      expect(mockGetFrame).toHaveBeenCalledTimes(2);
    });

    it("should use cache for previously loaded frames", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // First load
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Second load with same timestamp (100ms bucket)
      await act(async () => {
        await result.current.loadFrames(1000050000);
      });

      expect(mockGetFrame).toHaveBeenCalledTimes(1);
    });

    it("should handle API errors gracefully", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockGetFrame
        .mockResolvedValueOnce({ blobUrl: "blob:test-1", timestampNs: 1000 })
        .mockRejectedValueOnce(new Error("Network error"));

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Should have one frame, one failed
      expect(result.current.frames.size).toBe(1);
      expect(result.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(result.current.frames.has("/camera/image2")).toBe(false);

      consoleSpy.mockRestore();
    });

    it("should set loading state during request", async () => {
      let resolveFrame: (value: any) => void;
      const framePromise = new Promise((resolve) => {
        resolveFrame = resolve;
      });
      mockGetFrame.mockReturnValue(framePromise as any);

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      act(() => {
        result.current.loadFrames(1000000000);
      });

      expect(result.current.isLoading).toBe(true);

      await act(async () => {
        resolveFrame!({ blobUrl: "blob:test", timestampNs: 1000 });
        await framePromise;
      });

      expect(result.current.isLoading).toBe(false);
    });

    it("should cancel pending requests on new load", async () => {
      const abortSpy = vi.spyOn(AbortController.prototype, "abort");
      mockGetFrame.mockImplementation(() => new Promise(() => {})); // Never resolve

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      act(() => {
        result.current.loadFrames(1000000000);
      });

      act(() => {
        result.current.loadFrames(2000000000);
      });

      expect(abortSpy).toHaveBeenCalled();
    });

    it("should do nothing when topics array is empty", async () => {
      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "test-episode", topics: [] })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(mockGetFrame).not.toHaveBeenCalled();
    });

    it("should handle different episodes independently", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result: result1 } = renderHook(() =>
        useMcapFrames({
          episodeId: "episode-1",
          topics: ["/camera/image1"],
        })
      );

      const { result: result2 } = renderHook(() =>
        useMcapFrames({
          episodeId: "episode-2",
          topics: ["/camera/image1"],
        })
      );

      await act(async () => {
        await result1.current.loadFrames(1000000000);
        await result2.current.loadFrames(1000000000);
      });

      expect(result1.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(result2.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(mockGetFrame).toHaveBeenCalledTimes(2);
    });
  });

  describe("preloadFrames", () => {
    it("should preload frames without updating state", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:preloaded",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      expect(mockGetFrame).toHaveBeenCalled();
      expect(result.current.frames.size).toBe(0); // State not updated
    });

    it("should ignore preload errors", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockGetFrame.mockRejectedValue(new Error("Network error"));

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // Should not throw
      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      consoleSpy.mockRestore();
    });

    it("should skip already cached topics", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // Load first
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Preload same timestamp
      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      expect(mockGetFrame).toHaveBeenCalledTimes(1);
    });
  });

  describe("cleanup", () => {
    it("should revoke blob URLs on unmount", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result, unmount } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      unmount();

      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-1");
    });

    it("should revoke multiple blob URLs on unmount", async () => {
      let callCount = 0;
      mockGetFrame.mockImplementation(() => {
        callCount++;
        return Promise.resolve({
          blobUrl: `blob:test-${callCount}`,
          timestampNs: 1000000000,
        });
      });

      const { result, unmount } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2", "/camera/image3"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      unmount();

      expect(URL.revokeObjectURL).toHaveBeenCalledTimes(3);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-1");
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-2");
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-3");
    });
  });

  describe("concurrency", () => {
    it("should limit concurrent requests to MAX_CONCURRENT", async () => {
      let activeRequests = 0;
      let maxActiveRequests = 0;

      mockGetFrame.mockImplementation(async () => {
        activeRequests++;
        maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
        await new Promise((resolve) => setTimeout(resolve, 10));
        activeRequests--;
        return { blobUrl: "blob:test", timestampNs: 1000 };
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: Array(10).fill("/camera/image").map((t, i) => `${t}${i}`),
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(maxActiveRequests).toBeLessThanOrEqual(3);
    });

    it("should handle rapid successive calls", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // Rapid successive calls
      await act(async () => {
        result.current.loadFrames(1000000000);
        result.current.loadFrames(2000000000);
        result.current.loadFrames(3000000000);
      });

      // Should only have the last call's results eventually
      await waitFor(() => {
        expect(mockGetFrame).toHaveBeenCalled();
      });
    });
  });

  describe("cache key calculation", () => {
    it("should use 100ms buckets for caching", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // These timestamps should all fall in the same 100ms bucket
      const timestamps = [
        1000000000,
        1000050000,
        1000099999,
        1000100000 - 1,
      ];

      for (const ts of timestamps) {
        await act(async () => {
          await result.current.loadFrames(ts);
        });
      }

      // Should only call API once for all timestamps in same bucket
      expect(mockGetFrame).toHaveBeenCalledTimes(1);
    });

    it("should use different cache buckets for different timestamps", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // These timestamps should fall in different 100ms buckets
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      await act(async () => {
        await result.current.loadFrames(1000100000);
      });

      await act(async () => {
        await result.current.loadFrames(1000200000);
      });

      expect(mockGetFrame).toHaveBeenCalledTimes(3);
    });

    it("should include topic name in cache key", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Should call API twice (once per topic)
      expect(mockGetFrame).toHaveBeenCalledTimes(2);
    });
  });
});
