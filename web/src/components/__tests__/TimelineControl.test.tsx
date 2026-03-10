import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TimelineControl } from "../TimelineControl";

describe("TimelineControl", () => {
  const defaultProps = {
    currentTime: 5000000000, // 5s in ns
    duration: 60, // 60s
    isPlaying: false,
    playbackRate: 1,
    onSeek: vi.fn(),
    onPlay: vi.fn(),
    onPause: vi.fn(),
    onRateChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("time display", () => {
    it("should display current time", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("00:05.000")).toBeInTheDocument();
    });

    it("should display total duration", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("01:00.000")).toBeInTheDocument();
    });

    it("should format times correctly", () => {
      const { rerender } = render(
        <TimelineControl {...defaultProps} currentTime={12500000000} duration={125} />
      );

      expect(screen.getByText("00:12.500")).toBeInTheDocument();
      expect(screen.getByText("02:05.000")).toBeInTheDocument();
    });

    it("should format zero time correctly", () => {
      render(<TimelineControl {...defaultProps} currentTime={0} duration={0} />);

      expect(screen.getByText("00:00.000")).toBeInTheDocument();
    });

    it("should format large times correctly", () => {
      render(<TimelineControl {...defaultProps} currentTime={3661000000000} duration={3661} />);

      expect(screen.getByText("61:01.000")).toBeInTheDocument();
    });
  });

  describe("progress bar", () => {
    it("should show correct progress", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]') as HTMLInputElement;
      expect(slider.value).toBe("8.33"); // 5/60 * 100
    });

    it("should handle zero duration", () => {
      const { container } = render(
        <TimelineControl {...defaultProps} duration={0} />
      );

      const slider = container.querySelector('input[type="range"]') as HTMLInputElement;
      expect(slider.value).toBe("0");
    });

    it("should call onSeek when slider changes", () => {
      const onSeek = vi.fn();
      const { container } = render(
        <TimelineControl {...defaultProps} onSeek={onSeek} />
      );

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.change(slider, { target: { value: "50" } });

      expect(onSeek).toHaveBeenCalledWith(30000000000); // 50% of 60s in ns
    });

    it("should call onSeek with zero when slider at start", () => {
      const onSeek = vi.fn();
      const { container } = render(
        <TimelineControl {...defaultProps} onSeek={onSeek} />
      );

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.change(slider, { target: { value: "0" } });

      expect(onSeek).toHaveBeenCalledWith(0);
    });

    it("should call onSeek with max when slider at end", () => {
      const onSeek = vi.fn();
      const { container } = render(
        <TimelineControl {...defaultProps} onSeek={onSeek} />
      );

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.change(slider, { target: { value: "100" } });

      expect(onSeek).toHaveBeenCalledWith(60000000000); // 60s in ns
    });

    it("should have correct slider attributes", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]') as HTMLInputElement;
      expect(slider.min).toBe("0");
      expect(slider.max).toBe("100");
      expect(slider.step).toBe("0.1");
    });
  });

  describe("play/pause controls", () => {
    it("should show Play button when paused", () => {
      render(<TimelineControl {...defaultProps} isPlaying={false} />);

      expect(screen.getByText("▶ Play")).toBeInTheDocument();
    });

    it("should show Pause button when playing", () => {
      render(<TimelineControl {...defaultProps} isPlaying={true} />);

      expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
    });

    it("should call onPlay when Play clicked", () => {
      const onPlay = vi.fn();
      render(<TimelineControl {...defaultProps} onPlay={onPlay} isPlaying={false} />);

      fireEvent.click(screen.getByText("▶ Play"));

      expect(onPlay).toHaveBeenCalled();
    });

    it("should call onPause when Pause clicked", () => {
      const onPause = vi.fn();
      render(<TimelineControl {...defaultProps} onPause={onPause} isPlaying={true} />);

      fireEvent.click(screen.getByText("⏸ Pause"));

      expect(onPause).toHaveBeenCalled();
    });

    it("should toggle between Play and Pause", () => {
      const { rerender } = render(<TimelineControl {...defaultProps} isPlaying={false} />);

      expect(screen.getByText("▶ Play")).toBeInTheDocument();
      expect(screen.queryByText("⏸ Pause")).not.toBeInTheDocument();

      rerender(<TimelineControl {...defaultProps} isPlaying={true} />);

      expect(screen.queryByText("▶ Play")).not.toBeInTheDocument();
      expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
    });
  });

  describe("skip buttons", () => {
    it("should skip backward 5s", () => {
      const onSeek = vi.fn();
      render(<TimelineControl {...defaultProps} onSeek={onSeek} />);

      fireEvent.click(screen.getByTitle("Back 5s"));

      expect(onSeek).toHaveBeenCalledWith(0); // 5s - 5s = 0
    });

    it("should skip forward 5s", () => {
      const onSeek = vi.fn();
      render(<TimelineControl {...defaultProps} onSeek={onSeek} />);

      fireEvent.click(screen.getByTitle("Forward 5s"));

      expect(onSeek).toHaveBeenCalledWith(10000000000); // 5s + 5s = 10s in ns
    });

    it("should clamp to 0 when skipping backward past start", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={2000000000} />
      );

      fireEvent.click(screen.getByTitle("Back 5s"));

      expect(onSeek).toHaveBeenCalledWith(0);
    });

    it("should clamp to duration when skipping forward past end", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={58000000000} />
      );

      fireEvent.click(screen.getByTitle("Forward 5s"));

      expect(onSeek).toHaveBeenCalledWith(60000000000); // clamped to 60s
    });

    it("should not go below 0 when already at start", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={0} />
      );

      fireEvent.click(screen.getByTitle("Back 5s"));

      expect(onSeek).toHaveBeenCalledWith(0);
    });

    it("should not go above duration when already at end", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={60000000000} />
      );

      fireEvent.click(screen.getByTitle("Forward 5s"));

      expect(onSeek).toHaveBeenCalledWith(60000000000);
    });
  });

  describe("playback rate", () => {
    it("should display all rate options", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("0.5x")).toBeInTheDocument();
      expect(screen.getByText("1x")).toBeInTheDocument();
      expect(screen.getByText("2x")).toBeInTheDocument();
    });

    it("should highlight current rate", () => {
      render(<TimelineControl {...defaultProps} playbackRate={2} />);

      const rateButton = screen.getByText("2x");
      expect(rateButton).toHaveClass("bg-blue-600");
    });

    it("should call onRateChange when rate clicked", () => {
      const onRateChange = vi.fn();
      render(<TimelineControl {...defaultProps} onRateChange={onRateChange} />);

      fireEvent.click(screen.getByText("0.5x"));

      expect(onRateChange).toHaveBeenCalledWith(0.5);
    });

    it("should call onRateChange with correct value for each rate", () => {
      const onRateChange = vi.fn();
      render(<TimelineControl {...defaultProps} onRateChange={onRateChange} />);

      fireEvent.click(screen.getByText("0.5x"));
      expect(onRateChange).toHaveBeenCalledWith(0.5);

      fireEvent.click(screen.getByText("1x"));
      expect(onRateChange).toHaveBeenCalledWith(1);

      fireEvent.click(screen.getByText("2x"));
      expect(onRateChange).toHaveBeenCalledWith(2);
    });

    it("should update highlighted rate when prop changes", () => {
      const { rerender } = render(<TimelineControl {...defaultProps} playbackRate={1} />);

      expect(screen.getByText("1x")).toHaveClass("bg-blue-600");

      rerender(<TimelineControl {...defaultProps} playbackRate={2} />);

      expect(screen.getByText("2x")).toHaveClass("bg-blue-600");
      expect(screen.getByText("1x")).not.toHaveClass("bg-blue-600");
    });
  });

  describe("dragging indicator", () => {
    it("should show time tooltip when dragging", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.mouseDown(slider);

      expect(screen.getAllByText("00:05.000").length).toBeGreaterThanOrEqual(1);
    });

    it("should hide tooltip when not dragging", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.mouseDown(slider);
      fireEvent.mouseUp(slider);

      // After mouse up, should only have the time display, not the tooltip
      expect(screen.getAllByText("00:05.000").length).toBe(1);
    });
  });

  describe("prop updates", () => {
    it("should update progress when currentTime changes", () => {
      const { rerender, container } = render(
        <TimelineControl {...defaultProps} currentTime={0} />
      );

      let slider = container.querySelector('input[type="range"]') as HTMLInputElement;
      expect(slider.value).toBe("0");

      rerender(<TimelineControl {...defaultProps} currentTime={30000000000} />);

      slider = container.querySelector('input[type="range"]') as HTMLInputElement;
      expect(slider.value).toBe("50");
    });

    it("should update time display when currentTime changes", () => {
      const { rerender } = render(
        <TimelineControl {...defaultProps} currentTime={0} />
      );

      expect(screen.getByText("00:00.000")).toBeInTheDocument();

      rerender(<TimelineControl {...defaultProps} currentTime={30000000000} />);

      expect(screen.getByText("00:30.000")).toBeInTheDocument();
    });
  });
});
