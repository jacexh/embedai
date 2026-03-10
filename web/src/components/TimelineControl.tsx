"use client";

import { useCallback, useState } from "react";

interface TimelineControlProps {
  currentTime: number; // nanoseconds
  duration: number; // seconds
  isPlaying: boolean;
  playbackRate: number;
  onSeek: (timeNs: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onRateChange: (rate: number) => void;
}

const PLAYBACK_RATES = [0.5, 1, 2];

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${mins.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}.${ms.toString().padStart(3, "0")}`;
}

export function TimelineControl({
  currentTime,
  duration,
  isPlaying,
  playbackRate,
  onSeek,
  onPlay,
  onPause,
  onRateChange,
}: TimelineControlProps) {
  const [isDragging, setIsDragging] = useState(false);

  const currentSeconds = currentTime / 1_000_000_000;
  const progress = duration > 0 ? (currentSeconds / duration) * 100 : 0;

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newProgress = parseFloat(e.target.value);
      const newTime = (newProgress / 100) * duration * 1_000_000_000;
      onSeek(newTime);
    },
    [duration, onSeek]
  );

  const handleSkip = useCallback(
    (seconds: number) => {
      const newTime = currentTime + seconds * 1_000_000_000;
      onSeek(Math.max(0, Math.min(newTime, duration * 1_000_000_000)));
    },
    [currentTime, duration, onSeek]
  );

  return (
    <div className="bg-gray-900 text-white p-4 rounded-lg">
      {/* Time display */}
      <div className="flex justify-between text-sm font-mono mb-2">
        <span>{formatTime(currentSeconds)}</span>
        <span>{formatTime(duration)}</span>
      </div>

      {/* Progress bar */}
      <div className="relative mb-4">
        <input
          type="range"
          min="0"
          max="100"
          step="0.1"
          value={progress}
          onChange={handleSliderChange}
          onMouseDown={() => setIsDragging(true)}
          onMouseUp={() => setIsDragging(false)}
          onTouchStart={() => setIsDragging(true)}
          onTouchEnd={() => setIsDragging(false)}
          className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
        />
        {isDragging && (
          <div
            className="absolute top-6 bg-gray-800 text-xs px-2 py-1 rounded transform -translate-x-1/2"
            style={{ left: `${progress}%` }}
          >
            {formatTime(currentSeconds)}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSkip(-5)}
            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            title="Back 5s"
          >
            ← 5s
          </button>

          <button
            onClick={isPlaying ? onPause : onPlay}
            className="px-4 py-1 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium"
          >
            {isPlaying ? "⏸ Pause" : "▶ Play"}
          </button>

          <button
            onClick={() => handleSkip(5)}
            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            title="Forward 5s"
          >
            5s →
          </button>
        </div>

        {/* Playback rate */}
        <div className="flex items-center gap-1">
          {PLAYBACK_RATES.map((rate) => (
            <button
              key={rate}
              onClick={() => onRateChange(rate)}
              className={`px-2 py-1 text-xs rounded ${
                playbackRate === rate
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 hover:bg-gray-600"
              }`}
            >
              {rate}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
