"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEpisode } from "@/api/episodes";
import { useMcapFrames } from "@/hooks/useMcapFrames";
import { VideoGrid } from "@/components/VideoGrid";
import { TimelineControl } from "@/components/TimelineControl";
import { Spinner } from "@/components/Spinner";

// Simple debounce hook
function useDebounce<T extends (...args: any[]) => void>(
  fn: T,
  delay: number
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  return useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        fn(...args);
      }, delay);
    },
    [fn, delay]
  ) as T;
}

// Filter image topics from episode
function getImageTopics(episode: ReturnType<typeof useEpisode>["data"]): string[] {
  if (!episode?.topics) return [];

  return episode.topics
    .filter(
      (t) =>
        t.type === "image" ||
        t.schema_name?.includes("Image") ||
        t.name.includes("camera") ||
        t.name.includes("image")
    )
    .map((t) => t.name);
}

export function PreviewPage() {
  const { episodeId } = useParams<{ episodeId: string }>();
  const navigate = useNavigate();
  const { data: episode, isLoading: isLoadingEpisode } = useEpisode(episodeId!);

  // Memoize to avoid new array reference every render (would cause infinite loops)
  const imageTopics = useMemo(() => getImageTopics(episode), [episode]);
  const duration = episode?.duration_seconds ?? 0;

  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const { frames, isLoading: isLoadingFrames, loadFrames } = useMcapFrames({
    episodeId: episodeId!,
    topics: imageTopics,
  });

  // Debounced frame loading to prevent browser resource exhaustion
  const debouncedLoadFrames = useDebounce(loadFrames, 150);

  const animationRef = useRef<number | undefined>(undefined);
  const lastFrameTimeRef = useRef<number>(0);
  const lastLoadedTimeRef = useRef<number>(-1); // Track last loaded frame time

  // Initial load - get first frame
  useEffect(() => {
    if (imageTopics.length > 0 && episode?.duration_seconds) {
      loadFrames(0);
    }
  }, [imageTopics, episode?.duration_seconds, loadFrames]);

  // Handle play/pause animation
  useEffect(() => {
    if (!isPlaying) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      return;
    }

    const animate = (timestamp: number) => {
      if (lastFrameTimeRef.current === 0) {
        lastFrameTimeRef.current = timestamp;
      }

      const deltaTime = (timestamp - lastFrameTimeRef.current) / 1000; // seconds
      lastFrameTimeRef.current = timestamp;

      setCurrentTime((prev) => {
        const newTime = Math.round(prev + deltaTime * playbackRate * 1_000_000_000);
        const maxTime = Math.round(duration * 1_000_000_000);

        if (newTime >= maxTime) {
          setIsPlaying(false);
          return maxTime;
        }

        return newTime;
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    lastFrameTimeRef.current = 0;
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, playbackRate, duration]);

  // Load frames when currentTime changes
  // During playback, only load if we've advanced >= 200ms since last load
  useEffect(() => {
    const PLAYBACK_FRAME_INTERVAL_NS = 500_000_000; // 500ms in nanoseconds
    if (
      !isPlaying ||
      lastLoadedTimeRef.current < 0 ||
      Math.abs(currentTime - lastLoadedTimeRef.current) >= PLAYBACK_FRAME_INTERVAL_NS
    ) {
      lastLoadedTimeRef.current = currentTime;
      debouncedLoadFrames(currentTime);
    }
  }, [currentTime, isPlaying, debouncedLoadFrames]);

  const handleSeek = useCallback(
    (timeNs: number) => {
      lastLoadedTimeRef.current = -1; // Force immediate load on seek
      setCurrentTime(timeNs);
      setIsPlaying(false);
      debouncedLoadFrames(timeNs);
    },
    [debouncedLoadFrames]
  );

  const handlePlay = useCallback(() => {
    setIsPlaying(true);
  }, []);

  const handlePause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  if (isLoadingEpisode) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <p className="text-red-500 mb-4">Episode not found</p>
          <button
            onClick={() => navigate("/episodes")}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Back to Episodes
          </button>
        </div>
      </div>
    );
  }

  if (episode.format !== "mcap") {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <p className="text-gray-600 mb-4">
            Preview is only available for MCAP files
          </p>
          <button
            onClick={() => navigate("/episodes")}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Back to Episodes
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/episodes")}
              className="text-gray-600 hover:text-gray-900"
            >
              ← Back
            </button>
            <h1 className="text-xl font-semibold text-gray-900">
              {episode.filename}
            </h1>
          </div>
          <div className="text-sm text-gray-500">
            Duration: {Math.floor(duration / 60)}m {Math.floor(duration % 60)}s
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="p-6 max-w-7xl mx-auto">
        {/* Video grid */}
        <div className="mb-6">
          <VideoGrid
            topics={imageTopics}
            frames={frames}
            isLoading={isLoadingFrames}
          />
        </div>

        {/* Timeline */}
        <TimelineControl
          currentTime={currentTime}
          duration={duration}
          isPlaying={isPlaying}
          playbackRate={playbackRate}
          onSeek={handleSeek}
          onPlay={handlePlay}
          onPause={handlePause}
          onRateChange={setPlaybackRate}
        />
      </div>
    </div>
  );
}
