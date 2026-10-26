import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TrackResult } from "../../api/types";
import { TrackRow } from "./TrackRow";

const baseTrack: TrackResult = {
  title: "Tum Hi Ho",
  artist: "Arijit Singh",
  url: "https://music.amazon.com/tracks/B002TRACK",
};

describe("TrackRow library status", () => {
  it("labels an exact library match without relying on color", () => {
    render(
      <TrackRow
        track={{
          ...baseTrack,
          in_library: true,
          library_match: "exact",
        }}
      />,
    );

    expect(screen.getByText("In library")).toHaveAttribute(
      "title",
      "Exact match in your library",
    );
  });

  it("labels a likely match and omits the badge when the index is incomplete", () => {
    const { rerender } = render(
      <TrackRow
        track={{
          ...baseTrack,
          in_library: true,
          library_match: "likely",
        }}
      />,
    );

    expect(screen.getByText("In library")).toHaveAttribute(
      "title",
      "Likely match in your library",
    );

    rerender(<TrackRow track={{ ...baseTrack, in_library: null }} />);
    expect(screen.queryByText("In library")).not.toBeInTheDocument();
  });
});
