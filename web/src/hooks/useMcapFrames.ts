"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import axios from "axios";
import { getFrame } from "@/api/episodes";

interface UseMcapFramesOptions {
  episodeId: string;
  topics: string[];
}

interface FrameCache {
  [key: string]: string; // topic_timestamp -> blobUrl
}

const CACHE_KEY = (topic: string, timestamp: number): string =>
  `${topic}_${Math.floor(timestamp / 100_000_000)}`; // 100ms buckets

// Limit concurrent requests to avoid browser resource exhaustion.
// Chrome allows 6 connections per host (HTTP/1.1). With multiple image topics
// (e.g. 6 cameras) and overlapping loadFrames calls (initial + debounced), peak
// connections could reach MAX_CONCURRENT * 2. Keep at 2 to stay well under 6.
const MAX_CONCURRENT = 2;

async function runWithConcurrency<T>(
  items: T[],
  fn: (item: T) => Promise<void>,
  concurrency: number
): Promise<void> {
  const executing: Promise<void>[] = [];

  for (const item of items) {
    // Wrap to self-remove from executing when done
    const task: Promise<void> = fn(item).finally(() => {
      const idx = executing.indexOf(task);
      if (idx !== -1) executing.splice(idx, 1);
    });
    executing.push(task);

    if (executing.length >= concurrency) {
      await Promise.race(executing);
    }
  }

  await Promise.all(executing);
}

export function useMcapFrames({ episodeId, topics }: UseMcapFramesOptions) {
  const [frames, setFrames] = useState<Map<string, string>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const cacheRef = useRef<FrameCache>({});
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(cacheRef.current).forEach((url) => {
        URL.revokeObjectURL(url);
      });
    };
  }, []);

  const loadFrames = useCallback(
    async (timestamp: number) => {
      if (topics.length === 0) return;

      // Cancel pending requests
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      // Capture controller locally so stale callbacks never read the updated ref
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsLoading(true);

      try {
        const newFrames = new Map<string, string>();

        await runWithConcurrency(
          topics,
          async (topic) => {
            // If this call was superseded before this topic's slot opened, skip it.
            // Without this guard, queued topics from a stale loadFrames call would
            // start using the new controller's signal, causing duplicate concurrent
            // requests that exhaust the browser's per-host connection limit.
            if (controller.signal.aborted) return;

            const cacheKey = CACHE_KEY(topic, timestamp);

            // Check cache first
            if (cacheRef.current[cacheKey]) {
              newFrames.set(topic, cacheRef.current[cacheKey]);
              return;
            }

            try {
              // Don't pass the signal to the HTTP layer. Passing it causes in-flight
              // requests to be cancelled when a new loadFrames call fires during
              // playback, which means frames never update (every request gets
              // cancelled before completing). The abort guard above already prevents
              // QUEUED (not-yet-started) topics from starting new requests — that is
              // sufficient to avoid connection exhaustion.
              const result = await getFrame(episodeId, { topic, timestamp });
              newFrames.set(topic, result.blobUrl);
              cacheRef.current[cacheKey] = result.blobUrl;
            } catch (error) {
              if (axios.isCancel(error)) {
                // Request was cancelled, ignore
                return;
              }
              console.error(`Failed to load frame for ${topic}:`, error);
              // Leave empty for failed topics
            }
          },
          MAX_CONCURRENT
        );

        // Update state whenever we got results, even if a newer call is pending.
        // The abort guard above already ensures stale calls don't FIRE new requests;
        // allowing their completed results through keeps the animation responsive.
        if (newFrames.size > 0) {
          setFrames(newFrames);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    },
    [episodeId, topics]
  );

  const preloadFrames = useCallback(
    async (timestamp: number) => {
      if (topics.length === 0) return;

      // Preload with lower concurrency
      await runWithConcurrency(
        topics,
        async (topic) => {
          const cacheKey = CACHE_KEY(topic, timestamp);
          if (cacheRef.current[cacheKey]) return;

          try {
            const result = await getFrame(
              episodeId,
              { topic, timestamp },
              abortControllerRef.current?.signal
            );
            cacheRef.current[cacheKey] = result.blobUrl;
          } catch (error) {
            if (axios.isCancel(error)) {
              // Request was cancelled, ignore
              return;
            }
            // Ignore other preload errors
          }
        },
        MAX_CONCURRENT
      );
    },
    [episodeId, topics]
  );

  return {
    frames,
    isLoading,
    loadFrames,
    preloadFrames,
  };
}
