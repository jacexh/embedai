"use client";

import { useState, useCallback, useRef, useEffect } from "react";
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

// Limit concurrent requests to avoid browser resource exhaustion
const MAX_CONCURRENT = 3;

async function runWithConcurrency<T>(
  items: T[],
  fn: (item: T) => Promise<void>,
  concurrency: number
): Promise<void> {
  const executing: Promise<void>[] = [];

  for (const item of items) {
    const promise = fn(item);
    executing.push(promise);

    if (executing.length >= concurrency) {
      await Promise.race(executing);
      executing.splice(
        executing.findIndex((p) => p === promise),
        1
      );
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
      abortControllerRef.current = new AbortController();

      setIsLoading(true);

      try {
        const newFrames = new Map<string, string>();

        await runWithConcurrency(
          topics,
          async (topic) => {
            const cacheKey = CACHE_KEY(topic, timestamp);

            // Check cache first
            if (cacheRef.current[cacheKey]) {
              newFrames.set(topic, cacheRef.current[cacheKey]);
              return;
            }

            try {
              const result = await getFrame(episodeId, { topic, timestamp });
              newFrames.set(topic, result.blobUrl);
              cacheRef.current[cacheKey] = result.blobUrl;
            } catch (error) {
              console.error(`Failed to load frame for ${topic}:`, error);
              // Leave empty for failed topics
            }
          },
          MAX_CONCURRENT
        );

        setFrames(newFrames);
      } finally {
        setIsLoading(false);
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
            const result = await getFrame(episodeId, { topic, timestamp });
            cacheRef.current[cacheKey] = result.blobUrl;
          } catch {
            // Ignore preload errors
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
