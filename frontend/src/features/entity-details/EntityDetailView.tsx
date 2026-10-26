import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchEntityDetail } from "../../api/client";
import { errorMessage, errorRequestId } from "../../api/errors";
import type {
  CatalogItem,
  EntityDetail,
  TrackResult,
} from "../../api/types";
import { CatalogCard } from "../../components/catalog/CatalogCard";
import { TrackRow } from "../../components/catalog/TrackRow";
import {
  BackIcon,
  DownloadIcon,
  MusicIcon,
} from "../../components/icons";
import { Artwork } from "../../components/ui/Artwork";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHeading } from "../../components/ui/SectionHeading";
import { kindLabel } from "../catalog/labels";
import { useEnqueueBatch, useEnqueueTrack } from "../queue/hooks";
import { useUIStore } from "../../state/uiStore";

function DetailSkeleton() {
  return (
    <div className="detail-skeleton" aria-busy="true">
      <span className="visually-hidden">Loading details…</span>
      <div className="skeleton skeleton--hero" aria-hidden="true" />
      <div className="skeleton skeleton--heading" aria-hidden="true" />
      <div className="skeleton skeleton--row" aria-hidden="true" />
      <div className="skeleton skeleton--row" aria-hidden="true" />
    </div>
  );
}

function DetailContent({
  detail,
  onOpen,
  headingRef,
  onDownloadTrack,
  downloadBusyUrl,
  downloadDisabled,
  onDownloadAll,
  bulkPending,
}: {
  detail: EntityDetail;
  onOpen: (url: string) => void;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onDownloadTrack: (track: TrackResult) => void;
  downloadBusyUrl?: string;
  downloadDisabled: boolean;
  onDownloadAll: () => void;
  bulkPending: boolean;
}) {
  const artist = detail.kind === "artist";
  const albumItems: CatalogItem[] = detail.albums.map((album) => ({
    title: album.title,
    subtitle: album.subtitle,
    url: album.url,
    image: album.image,
    kind: "album",
  }));

  return (
    <>
      <header className={`detail-hero ${artist ? "detail-hero--artist" : ""}`.trim()}>
        <Artwork
          src={detail.image}
          alt=""
          shape={artist ? "circle" : "square"}
          className="detail-hero__art"
        />
        <div className="detail-hero__body">
          <p className="eyebrow">{kindLabel(detail.kind)}</p>
          <h1 ref={headingRef} tabIndex={-1}>
            {detail.title}
          </h1>
          {detail.subtitle ? <p className="detail-hero__subtitle">{detail.subtitle}</p> : null}
          {detail.tracks.length > 0 ? (
            <div className="detail-hero__actions">
              <Button
                variant="primary"
                icon={<DownloadIcon />}
                onClick={onDownloadAll}
                disabled={bulkPending}
              >
                {artist
                  ? `Download top tracks (${detail.tracks.length})`
                  : `Download all (${detail.tracks.length})`}
              </Button>
            </div>
          ) : null}
        </div>
      </header>

      {artist && albumItems.length > 0 ? (
        <section className="detail-section" aria-label="Albums">
          <SectionHeading title="Albums" count={albumItems.length} />
          <div className="card-grid">
            {albumItems.map((album) => (
              <CatalogCard key={album.url} item={album} onOpen={onOpen} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="detail-section" aria-label={artist ? "Top tracks" : "Tracks"}>
        <SectionHeading
          title={artist ? "Top tracks" : "Tracks"}
          count={detail.tracks.length}
        />
        {detail.tracks.length > 0 ? (
          <div className="track-list">
            {detail.tracks.map((track, index) => (
              <TrackRow
                key={`${track.url}:${index}`}
                track={track}
                onDownload={onDownloadTrack}
                downloadBusy={downloadBusyUrl === track.url}
                downloadDisabled={downloadDisabled}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<MusicIcon />}
            title="No tracks found"
            description="This item did not return a track list."
          />
        )}
      </section>
    </>
  );
}

export function EntityDetailView({ url }: { url: string }) {
  const backToSearch = useUIStore((state) => state.backToSearch);
  const openDetail = useUIStore((state) => state.openDetail);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const enqueue = useEnqueueTrack();
  const enqueueBatch = useEnqueueBatch();
  const detail = useQuery({
    queryKey: ["entity", url],
    queryFn: ({ signal }) => fetchEntityDetail(url, signal),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const pendingUrl = enqueue.isPending ? enqueue.variables?.url : undefined;

  useEffect(() => {
    if (detail.data) {
      headingRef.current?.focus();
    }
  }, [detail.data]);

  const downloadTrack = (track: TrackResult) => {
    enqueue.mutate({
      url: track.url,
      title: track.title,
      artist: track.artist,
    });
  };

  const downloadAll = () => {
    if (!detail.data || detail.data.tracks.length === 0) {
      return;
    }
    enqueueBatch.mutate(
      detail.data.tracks.map((track) => ({
        url: track.url,
        title: track.title,
        artist: track.artist,
      })),
    );
  };

  return (
    <article className="detail-view">
      <div className="detail-toolbar">
        <Button
          variant="ghost"
          icon={<BackIcon />}
          onClick={backToSearch}
          aria-label="Back to search"
        >
          Back to search
        </Button>
      </div>
      {detail.isPending ? <DetailSkeleton /> : null}
      {detail.isError ? (
        <ErrorState
          title="Could not load details"
          message={errorMessage(detail.error)}
          requestId={errorRequestId(detail.error)}
          onRetry={() => {
            void detail.refetch();
          }}
          onBack={backToSearch}
        />
      ) : null}
      {detail.data ? (
        <DetailContent
          detail={detail.data}
          onOpen={openDetail}
          headingRef={headingRef}
          onDownloadTrack={downloadTrack}
          downloadBusyUrl={pendingUrl}
          downloadDisabled={enqueue.isPending}
          onDownloadAll={downloadAll}
          bulkPending={enqueueBatch.isPending}
        />
      ) : null}
    </article>
  );
}
