"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { getFrame, type FrameResult } from "@/api/episodes";

interface UseMcapFramesOptions {
  episodeId: string;
  topics: string[];
}

interface FrameCache {
  [key: string]: string; // topic_timestamp -> blobUrl
}

const CACHE_KEY = (topic: string, timestamp: number): string =>
  `${topic}_${Math.floor(timestamp / 100_000_000)}`; // 100ms buckets

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
        const requests = topics.map(async (topic) => {
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
        });

        await Promise.all(requests);
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

      topics.forEach(async (topic) => {
        const cacheKey = CACHE_KEY(topic, timestamp);
        if (cacheRef.current[cacheKey]) return;

        try {
          const result = await getFrame(episodeId, { topic, timestamp });
          cacheRef.current[cacheKey] = result.blobUrl;
        } catch {
          // Ignore preload errors
        }
      });
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
