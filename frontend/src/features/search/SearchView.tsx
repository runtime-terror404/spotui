import { useId } from "react";
import { useQuery } from "@tanstack/react-query";

import { searchAmazon } from "../../api/client";
import { errorMessage, errorRequestId } from "../../api/errors";
import type { SearchSection, TrackResult } from "../../api/types";
import { CatalogCard } from "../../components/catalog/CatalogCard";
import { TrackRow } from "../../components/catalog/TrackRow";
import { MusicIcon } from "../../components/icons";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { useUIStore } from "../../state/uiStore";
import { useEnqueueTrack } from "../queue/hooks";

function SearchSkeleton() {
  return (
    <div className="search-skeleton" aria-busy="true">
      <span className="visually-hidden">Searching Amazon Music…</span>
      {[0, 1, 2].map((section) => (
        <div className="skeleton-section" key={section} aria-hidden="true">
          <div className="skeleton skeleton--heading" />
          <div className="skeleton-grid">
            {[0, 1, 2, 3].map((card) => (
              <div className="skeleton skeleton--card" key={card} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ResultsSection({
  section,
  onOpen,
  onDownload,
  downloadBusyUrl,
  downloadDisabled,
}: {
  section: SearchSection;
  onOpen: (url: string) => void;
  onDownload: (track: TrackResult) => void;
  downloadBusyUrl?: string;
  downloadDisabled: boolean;
}) {
  const headingId = useId();
  return (
    <section className="result-section" aria-labelledby={headingId}>
      <div id={headingId}>
        <SectionHeading title={section.title} count={section.items.length} />
      </div>
      {section.kind === "track" ? (
        <div className="track-list">
          {section.items.map((item) => {
            const track: TrackResult = {
              title: item.title,
              artist: item.subtitle,
              url: item.url,
              image: item.image,
              in_library: item.in_library,
              library_match: item.library_match,
            };
            return (
              <TrackRow
                key={item.url}
                track={track}
                onDownload={onDownload}
                downloadBusy={downloadBusyUrl === item.url}
                downloadDisabled={downloadDisabled}
              />
            );
          })}
        </div>
      ) : (
        <div
          className={`card-grid ${
            section.kind === "artist" ? "card-grid--artists" : ""
          }`.trim()}
        >
          {section.items.map((item) => (
            <CatalogCard key={item.url} item={item} onOpen={onOpen} />
          ))}
        </div>
      )}
    </section>
  );
}

export function SearchView() {
  const submittedQuery = useUIStore((state) => state.submittedQuery);
  const openDetail = useUIStore((state) => state.openDetail);
  const setSearchScrollY = useUIStore((state) => state.setSearchScrollY);
  const enqueue = useEnqueueTrack();
  const pendingUrl = enqueue.isPending ? enqueue.variables?.url : undefined;

  const search = useQuery({
    queryKey: ["search", submittedQuery],
    queryFn: ({ signal }) => searchAmazon(submittedQuery, signal),
    enabled: submittedQuery.length > 0,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const open = (url: string) => {
    setSearchScrollY(window.scrollY);
    openDetail(url);
  };

  const downloadTrack = (track: TrackResult) => {
    enqueue.mutate({
      url: track.url,
      title: track.title,
      artist: track.artist,
    });
  };

  if (!submittedQuery) {
    return (
      <EmptyState
        icon={<MusicIcon />}
        title="Search Amazon Music"
        description="Find an artist, album, playlist, or song to explore in SpotUI."
      />
    );
  }

  if (search.isPending) {
    return <SearchSkeleton />;
  }

  if (search.isError) {
    return (
      <ErrorState
        title="Search failed"
        message={errorMessage(search.error)}
        requestId={errorRequestId(search.error)}
        onRetry={() => {
          void search.refetch();
        }}
      />
    );
  }

  const sections = search.data?.sections ?? [];
  const hasResults = sections.some((section) => section.items.length > 0);
  if (!hasResults) {
    return (
      <EmptyState
        icon={<MusicIcon />}
        title={`No results for “${submittedQuery}”`}
        description="Try a different spelling, a shorter query, or search for an artist instead."
      />
    );
  }

  return (
    <div className="search-results">
      <p className="results-summary" role="status" aria-live="polite">
        Results for <strong>{submittedQuery}</strong>
      </p>
      {sections.map((section) => (
        <ResultsSection
          key={`${section.kind}:${section.title}`}
          section={section}
          onOpen={open}
          onDownload={downloadTrack}
          downloadBusyUrl={pendingUrl}
          downloadDisabled={enqueue.isPending}
        />
      ))}
    </div>
  );
}
