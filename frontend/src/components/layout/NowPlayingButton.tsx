import { useMutation } from "@tanstack/react-query";

import { fetchNowPlaying } from "../../api/client";
import { errorMessage } from "../../api/errors";
import { useSnackbarStore } from "../../state/snackbarStore";
import { useUIStore } from "../../state/uiStore";
import { MusicIcon } from "../icons";

export function NowPlayingButton() {
  const nowPlaying = useMutation({
    mutationFn: () => fetchNowPlaying(),
  });
  const setInputQuery = useUIStore((state) => state.setInputQuery);
  const submitSearch = useUIStore((state) => state.submitSearch);
  const pushSnackbar = useSnackbarStore((state) => state.push);

  const onClick = async () => {
    try {
      const data = await nowPlaying.mutateAsync();
      if (data.track?.title) {
        setInputQuery(data.track.title);
        submitSearch(data.track.title);
        window.scrollTo({ top: 0, behavior: "auto" });
        return;
      }
      pushSnackbar(
        data.reason ??
          (data.available === false
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
      className="now-playing"
      aria-label="Search current track"
      title="Search current track"
      disabled={nowPlaying.isPending}
      onClick={() => {
        void onClick();
      }}
    >
      <MusicIcon />
    </button>
  );
}
