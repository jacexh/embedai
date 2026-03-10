"use client";

import { useMemo } from "react";

interface VideoTileProps {
  topic: string;
  frameUrl: string | undefined;
  isLoading: boolean;
}

function VideoTile({ topic, frameUrl, isLoading }: VideoTileProps) {
  return (
    <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
      {frameUrl ? (
        <img
          src={frameUrl}
          alt={topic}
          className="w-full h-full object-contain"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-gray-500">
          {isLoading ? (
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
          ) : (
            <span className="text-sm">No frame</span>
          )}
        </div>
      )}

      {/* Topic overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
        <span className="text-xs text-white font-mono truncate block">
          {topic}
        </span>
      </div>
    </div>
  );
}

interface VideoGridProps {
  topics: string[];
  frames: Map<string, string>;
  isLoading: boolean;
}

export function VideoGrid({ topics, frames, isLoading }: VideoGridProps) {
  const gridCols = useMemo(() => {
    const count = topics.length;
    if (count <= 1) return 1;
    if (count <= 2) return 2;
    if (count <= 4) return 2;
    if (count <= 6) return 3;
    if (count <= 9) return 3;
    return 4;
  }, [topics.length]);

  if (topics.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-gray-100 rounded-lg">
        <p className="text-gray-500">No image topics found in this episode</p>
      </div>
    );
  }

  return (
    <div
      className="grid gap-4"
      style={{
        gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
      }}
    >
      {topics.map((topic) => (
        <VideoTile
          key={topic}
          topic={topic}
          frameUrl={frames.get(topic)}
          isLoading={isLoading}
        />
      ))}
    </div>
  );
}
