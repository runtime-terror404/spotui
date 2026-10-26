import type { TrackResult } from "../../api/types";
import { Artwork } from "../ui/Artwork";

interface TrackRowProps {
  track: TrackResult;
}

export function TrackRow({ track }: TrackRowProps) {
  return (
    <div className="track-row">
      <Artwork
        src={track.image}
        alt=""
        shape="square"
        className="track-row__art"
      />
      <div className="track-row__body">
        <span className="track-row__title" title={track.title}>
          {track.title}
        </span>
        {track.artist ? (
          <span className="track-row__artist" title={track.artist}>
            {track.artist}
          </span>
        ) : null}
      </div>
      {track.in_library ? (
        <span className="library-badge">In library</span>
      ) : null}
    </div>
  );
}
