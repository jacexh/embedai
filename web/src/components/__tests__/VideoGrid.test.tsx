import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { VideoGrid } from "../VideoGrid";

describe("VideoGrid", () => {
  describe("empty state", () => {
    it("should show empty message when no topics", () => {
      render(<VideoGrid topics={[]} frames={new Map()} isLoading={false} />);

      expect(screen.getByText("No image topics found in this episode")).toBeInTheDocument();
    });
  });

  describe("grid layout", () => {
    it("should render single column for 1 topic", () => {
      const { container } = render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(1, minmax(0, 1fr))");
    });

    it("should render 2 columns for 2 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={["/camera/image1", "/camera/image2"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(2, minmax(0, 1fr))");
    });

    it("should render 2 columns for 4 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(4).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(2, minmax(0, 1fr))");
    });

    it("should render 3 columns for 6 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(6).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(3, minmax(0, 1fr))");
    });

    it("should render 4 columns for 10 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(10).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(4, minmax(0, 1fr))");
    });

    it("should render 4 columns for 12 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(12).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(4, minmax(0, 1fr))");
    });
  });

  describe("frame display", () => {
    it("should show loading spinner when loading", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={true}
        />
      );

      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    it("should show 'No frame' when not loading and no frame", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("No frame")).toBeInTheDocument();
    });

    it("should display frame image when available", () => {
      const frames = new Map([["/camera/image", "blob:test-frame"]]);

      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={frames}
          isLoading={false}
        />
      );

      const img = screen.getByAltText("/camera/image");
      expect(img).toHaveAttribute("src", "blob:test-frame");
    });

    it("should display topic name overlay", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("/camera/image")).toBeInTheDocument();
    });

    it("should handle multiple topics with mixed frame states", () => {
      const frames = new Map([
        ["/camera/image1", "blob:frame1"],
        // /camera/image2 has no frame
      ]);

      render(
        <VideoGrid
          topics={["/camera/image1", "/camera/image2"]}
          frames={frames}
          isLoading={false}
        />
      );

      expect(screen.getByAltText("/camera/image1")).toHaveAttribute("src", "blob:frame1");
      expect(screen.getAllByText("No frame").length).toBe(1);
    });

    it("should update when frames change", () => {
      const { rerender } = render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("No frame")).toBeInTheDocument();

      rerender(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map([["/camera/image", "blob:new-frame"]])}
          isLoading={false}
        />
      );

      expect(screen.getByAltText("/camera/image")).toHaveAttribute("src", "blob:new-frame");
    });
  });

  describe("topic rendering", () => {
    it("should render all topics with unique keys", () => {
      const topics = ["/camera/left", "/camera/right", "/depth/image"];

      render(
        <VideoGrid
          topics={topics}
          frames={new Map()}
          isLoading={false}
        />
      );

      topics.forEach((topic) => {
        expect(screen.getByText(topic)).toBeInTheDocument();
      });
    });

    it("should truncate long topic names", () => {
      const longTopic = "/very/long/topic/name/that/should/be/truncated";

      render(
        <VideoGrid
          topics={[longTopic]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const topicElement = screen.getByText(longTopic);
      expect(topicElement).toHaveClass("truncate");
    });

    it("should handle topic names with special characters", () => {
      const topics = ["/camera/image_raw", "/camera/image/compressed", "/depth/image_rect"];

      render(
        <VideoGrid
          topics={topics}
          frames={new Map()}
          isLoading={false}
        />
      );

      topics.forEach((topic) => {
        expect(screen.getByText(topic)).toBeInTheDocument();
      });
    });
  });

  describe("loading state changes", () => {
    it("should show loading then frame when loaded", () => {
      const { rerender } = render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={true}
        />
      );

      expect(screen.getByRole("status")).toBeInTheDocument();

      rerender(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map([["/camera/image", "blob:frame"]])}
          isLoading={false}
        />
      );

      expect(screen.getByAltText("/camera/image")).toBeInTheDocument();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("should show loading then no frame message when failed", () => {
      const { rerender } = render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={true}
        />
      );

      expect(screen.getByRole("status")).toBeInTheDocument();

      rerender(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("No frame")).toBeInTheDocument();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
