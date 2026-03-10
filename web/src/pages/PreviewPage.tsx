"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEpisode } from "@/api/episodes";
import { useMcapFrames } from "@/hooks/useMcapFrames";
import { VideoGrid } from "@/components/VideoGrid";
import { TimelineControl } from "@/components/TimelineControl";
import { Spinner } from "@/components/Spinner";

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

  const imageTopics = getImageTopics(episode);
  const duration = episode?.duration_seconds ?? 0;

  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const { frames, isLoading: isLoadingFrames, loadFrames } = useMcapFrames({
    episodeId: episodeId!,
    topics: imageTopics,
  });

  const animationRef = useRef<number>();
  const lastFrameTimeRef = useRef<number>(0);

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
        const newTime = prev + deltaTime * playbackRate * 1_000_000_000;
        const maxTime = duration * 1_000_000_000;

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

  // Load frames when currentTime changes (in pause mode or when playing)
  useEffect(() => {
    if (!isPlaying || currentTime % 10 === 0) {
      // Throttle frame loading during playback
      loadFrames(currentTime);
    }
  }, [currentTime, isPlaying, loadFrames]);

  const handleSeek = useCallback(
    (timeNs: number) => {
      setCurrentTime(timeNs);
      setIsPlaying(false);
      loadFrames(timeNs);
    },
    [loadFrames]
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
