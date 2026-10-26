import { useQuery } from "@tanstack/react-query";

import { fetchNowPlaying } from "../../api/client";
import { errorMessage } from "../../api/errors";
import { useSnackbarStore } from "../../state/snackbarStore";
import { useUIStore } from "../../state/uiStore";
import { MusicIcon } from "../icons";

export function NowPlayingButton() {
  const query = useQuery({
    queryKey: ["now-playing"],
    queryFn: ({ signal }) => fetchNowPlaying(signal),
    refetchInterval: 10_000,
    staleTime: 0,
    retry: false,
  });
  const setInputQuery = useUIStore((state) => state.setInputQuery);
  const submitSearch = useUIStore((state) => state.submitSearch);
  const pushSnackbar = useSnackbarStore((state) => state.push);
  const track = query.data?.track;

  const label = track
    ? `Search current track: ${track.title} by ${track.artist}`
    : "Now playing";

  const onClick = async () => {
    try {
      const result = await query.refetch();
      const data = result.data;
      if (data?.track?.title) {
        setInputQuery(data.track.title);
        submitSearch(data.track.title);
        window.scrollTo({ top: 0, behavior: "auto" });
        return;
      }
      pushSnackbar(
        data?.reason ??
          (data?.available === false
            ? "Now Playing is unavailable."
            : "Nothing is playing right now."),
        "info",
      );
    } catch (error) {
      pushSnackbar(errorMessage(error), "error");
    }
  };

  return (
    <button
      type="button"
      className={`now-playing ${track ? "is-playing" : ""}`.trim()}
      aria-label={label}
      title={label}
      disabled={query.isFetching}
      onClick={() => {
        void onClick();
      }}
    >
      <MusicIcon />
      <span className="now-playing__label">
        {track ? track.title : "Now playing"}
      </span>
    </button>
  );
}
