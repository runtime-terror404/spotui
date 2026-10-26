import type { TrackResult } from "../../api/types";
import { libraryMatchLabel } from "../../features/catalog/labels";
import { DownloadIcon } from "../icons";
import { Artwork } from "../ui/Artwork";

interface TrackRowProps {
  track: TrackResult;
  onDownload?: (track: TrackResult) => void;
  downloadBusy?: boolean;
  downloadDisabled?: boolean;
}

export function TrackRow({
  track,
  onDownload,
  downloadBusy = false,
  downloadDisabled = false,
}: TrackRowProps) {
  const downloadLabel = track.in_library
    ? `Download ${track.title} again`
    : `Download ${track.title}`;
  const matchLabel = libraryMatchLabel(track.library_match);

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
      <div className="track-row__actions">
        {track.in_library ? (
          <span
            className="library-badge"
            title={matchLabel}
            aria-label={matchLabel}
          >
            In library
          </span>
        ) : null}
        {onDownload ? (
          <button
            type="button"
            className="icon-button"
            aria-label={downloadLabel}
            title={downloadLabel}
            disabled={downloadDisabled}
            onClick={() => onDownload(track)}
          >
            <DownloadIcon />
          </button>
        ) : null}
      </div>
      {downloadBusy ? (
        <span className="visually-hidden" role="status">
          Adding to queue…
        </span>
      ) : null}
    </div>
  );
}
