import { errorMessage } from "../../api/errors";
import type { ImportSourceTrack } from "../../api/types";
import { Artwork } from "../../components/ui/Artwork";
import { Button } from "../../components/ui/Button";
import { CheckIcon, ClockIcon } from "../../components/icons";
import { useUIStore } from "../../state/uiStore";
import {
  useSearchImportSource,
  useSelectImportCandidate,
  useSkipImportSource,
} from "./hooks";
import { sourceStatusLabel, sourceStatusTone } from "./format";

export function ImportSourceRow({
  sessionId,
  source,
  displayPosition,
}: {
  sessionId: string;
  source: ImportSourceTrack;
  displayPosition: number;
}) {
  const select = useSelectImportCandidate(sessionId);
  const skip = useSkipImportSource(sessionId);
  const search = useSearchImportSource(sessionId);
  const openQueue = useUIStore((state) => state.openQueue);
  const locked =
    source.queue_outcome === "queued" || source.queue_outcome === "duplicate";
  const busy = select.isPending || skip.isPending || search.isPending;
  const actionError = select.error ?? skip.error ?? search.error;
  const canSearch =
    !locked &&
    source.review_status !== "selected" &&
    source.matching_status !== "searching" &&
    source.matching_status !== "pending";
  const statusTone = sourceStatusTone(source);

  return (
    <article className="import-track">
      <header className="import-track__header">
        <span className="import-track__position" aria-label={`Track ${displayPosition}`}>
          {displayPosition}
        </span>
        <div className="import-track__title-group">
          <h3 title={source.title}>{source.title}</h3>
          <p title={source.artist}>{source.artist || "Unknown artist"}</p>
        </div>
        <span className={`status-pill status-pill--${statusTone}`}>
          {sourceStatusLabel(source)}
        </span>
      </header>

      <div className="import-track__flags">
        {source.source_duplicate_of_id ? (
          <span className="data-flag data-flag--warning">
            Repeated occurrence in this Spotify list
          </span>
        ) : null}
        {source.queued_duplicate_of_source_id ? (
          <span className="data-flag data-flag--warning">
            Same Amazon track as another occurrence
          </span>
        ) : null}
        {source.library_match ? (
          <span className="data-flag">
            {source.library_match === "exact"
              ? "Exact match in your library"
              : "Likely match in your library"}
          </span>
        ) : null}
      </div>

      {source.matching_status === "pending" ||
      source.matching_status === "searching" ? (
        <div className="import-search-state" role="status">
          <ClockIcon />
          <span>
            {source.matching_status === "pending"
              ? "Waiting for an Amazon search slot…"
              : "Searching Amazon Music…"}
          </span>
          <span className="indeterminate-bar" aria-hidden="true" />
        </div>
      ) : null}

      {source.matching_status === "failed" ? (
        <div className="import-track__error" role="alert">
          <strong>Search failed</strong>
          <p>{source.last_error || "Amazon matching failed."}</p>
        </div>
      ) : null}

      {source.matching_status === "no_results" && source.review_status !== "skipped" ? (
        <p className="import-track__note">
          No Amazon candidates were found. Search again with the Spotify title and
          artist.
        </p>
      ) : null}

      {source.review_status === "skipped" ? (
        <p className="import-track__note">
          This occurrence is skipped and will not be queued.
        </p>
      ) : null}

      {source.candidates.length > 0 ? (
        <fieldset className="candidate-set">
          <legend className="visually-hidden">
            Amazon candidates for {source.title}
          </legend>
          <div className="candidate-list">
            {source.candidates.map((candidate) => {
              const selected = source.selected_candidate_id === candidate.id;
              return (
                <button
                  key={candidate.id}
                  type="button"
                  className={`candidate-card ${selected ? "is-selected" : ""}`.trim()}
                  aria-pressed={selected}
                  disabled={locked || busy}
                  onClick={() => {
                    select.mutate({
                      sourceId: source.id,
                      candidateId: candidate.id,
                    });
                  }}
                >
                  <span className="candidate-card__rank" aria-hidden="true">
                    {candidate.rank}
                  </span>
                  <Artwork
                    src={candidate.artwork_url}
                    alt=""
                    shape="square"
                    className="candidate-card__art"
                  />
                  <span className="candidate-card__body">
                    <span className="candidate-card__title" title={candidate.title}>
                      {candidate.title}
                    </span>
                    <span
                      className="candidate-card__artist"
                      title={candidate.artist}
                    >
                      {candidate.artist || "Unknown artist"}
                    </span>
                    <span
                      className="candidate-card__explanation"
                      title={candidate.explanation}
                    >
                      {candidate.explanation}
                    </span>
                    <span
                      className="candidate-card__score"
                      title="Relative matching score, not proof of an identical audio file"
                    >
                      {Math.round(candidate.score * 100)}% similarity
                    </span>
                  </span>
                  {selected ? (
                    <span className="candidate-card__selected">
                      <CheckIcon />
                      Selected
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </fieldset>
      ) : null}

      {actionError ? (
        <p className="inline-error" role="alert">
          {errorMessage(actionError)}
        </p>
      ) : null}

      <footer className="import-track__actions">
        {!locked && source.review_status !== "skipped" ? (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => skip.mutate(source.id)}
          >
            Skip
          </Button>
        ) : null}
        {canSearch ? (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => search.mutate(source.id)}
          >
            {search.isPending ? "Searching…" : "Search again"}
          </Button>
        ) : null}
        {locked ? (
          <Button
            variant="ghost"
            onClick={() => {
              openQueue();
            }}
          >
            View queue
          </Button>
        ) : null}
      </footer>
    </article>
  );
}
