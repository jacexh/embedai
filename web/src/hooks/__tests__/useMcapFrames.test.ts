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

    it("should update frames from in-flight requests even after a new loadFrames call starts", async () => {
      // This is the playback regression: when loadFrames fires faster than the backend
      // responds, every request gets cancelled before completing → frames never update.
      // The fix: don't pass the AbortSignal to the HTTP layer; only skip QUEUED topics.
      // The setFrames guard must also change from `!controller.signal.aborted` to
      // `newFrames.size > 0` so that results from in-flight requests are applied.
      // Mock resolves after 100ms and ignores the signal.
      mockGetFrame.mockImplementation(
        async () =>
          new Promise<{ blobUrl: string; timestampNs: number }>((resolve) => {
            setTimeout(() => resolve({ blobUrl: "blob:inflight", timestampNs: 0 }), 100);
          })
      );

      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "ep1", topics: ["/cam"] })
      );

      // Use act(async) so React flushes state updates from async continuations
      await act(async () => {
        result.current.loadFrames(0); // call 1: request starts, completes in 100ms
        await new Promise((r) => setTimeout(r, 30)); // 30ms in: abort call 1 by...
        result.current.loadFrames(1_000_000_000); // call 2: aborts controller_1
        // wait until call 1's 100ms request has completed (70ms more = 100ms total)
        await new Promise((r) => setTimeout(r, 80));
      });

      // Call 1's in-flight request completed (110ms after start) despite its
      // controller being aborted. frames must have been updated.
      expect(result.current.frames.size).toBe(1);
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

      expect(maxActiveRequests).toBeLessThanOrEqual(2);
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

    it("stale loadFrames should not exceed MAX_CONCURRENT using new controller signal", async () => {
      // Regression test for ERR_INSUFFICIENT_RESOURCES:
      // When loadFrames is called again while a previous call is still running its
      // runWithConcurrency queue, the stale call's queued topics must NOT use the
      // new call's AbortController signal (which is not yet aborted).
      // If they do, concurrent requests exceed MAX_CONCURRENT and Chrome hits its
      // per-host connection limit → ERR_INSUFFICIENT_RESOURCES.
      let concurrent = 0;
      let maxConcurrent = 0;

      mockGetFrame.mockImplementation(
        async (_id: string, _opts: any, signal?: AbortSignal) => {
          // Skip if already cancelled before we start
          if (signal?.aborted) {
            const err = new Error("canceled");
            (err as any).__CANCEL__ = true;
            throw err;
          }

          concurrent++;
          maxConcurrent = Math.max(maxConcurrent, concurrent);

          return new Promise<{ blobUrl: string; timestampNs: number }>(
            (resolve, reject) => {
              const timer = setTimeout(() => {
                concurrent--;
                resolve({ blobUrl: "blob:test", timestampNs: 0 });
              }, 30);

              signal?.addEventListener("abort", () => {
                clearTimeout(timer);
                concurrent--;
                const err = new Error("canceled");
                (err as any).__CANCEL__ = true;
                reject(err);
              });
            }
          );
        }
      );

      // 3 topics: A,B start immediately (MAX_CONCURRENT=2), C queues.
      // When loadFrames(t2) is called, t1's controller is aborted.
      // With the BUG: C from t1 starts using t2's controller (not aborted) → concurrent=3+
      // With the FIX: C from t1 checks its own aborted controller → skips.
      //   A,B from t1 are already in-flight (no HTTP abort) + A,B from t2 → peak ≤ 4 (2×MAX_CONCURRENT)
      const topics = ["/a", "/b", "/c"];
      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "ep1", topics })
      );

      act(() => {
        result.current.loadFrames(0); // t1: A,B start; C queues
        result.current.loadFrames(1_000_000_000); // t2: aborts t1, starts fresh
      });

      await waitFor(() => !result.current.isLoading, { timeout: 2000 });

      // Peak concurrency must not exceed 2×MAX_CONCURRENT (= 4):
      // at most MAX_CONCURRENT in-flight from t1 + MAX_CONCURRENT starting fresh in t2.
      // C from t1 must be skipped (abort guard), so concurrent never reaches 5+.
      expect(maxConcurrent).toBeLessThanOrEqual(4);
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

      // These timestamps fall in different 100ms buckets (each 100ms = 100_000_000 ns apart)
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      await act(async () => {
        await result.current.loadFrames(1100000000);
      });

      await act(async () => {
        await result.current.loadFrames(1200000000);
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
