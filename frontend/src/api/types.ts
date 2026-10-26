export type CatalogKind =
  | "artist"
  | "album"
  | "track"
  | "playlist"
  | "community_playlist";

export type LibraryMatch = "exact" | "likely";

export interface CatalogItem {
  title: string;
  subtitle: string;
  url: string;
  kind: CatalogKind;
  image?: string;
  in_library?: boolean | null;
  library_match?: LibraryMatch | null;
}

export interface SearchSection {
  title: string;
  kind: CatalogKind;
  items: CatalogItem[];
}

export interface SearchResponse {
  query: string;
  sections: SearchSection[];
}

export interface TrackResult {
  title: string;
  artist: string;
  url: string;
  image?: string;
  in_library?: boolean | null;
  library_match?: LibraryMatch | null;
}

export interface AlbumResult {
  title: string;
  subtitle: string;
  url: string;
  image?: string;
}

export interface EntityDetail {
  kind: CatalogKind;
  title: string;
  subtitle: string;
  image?: string;
  tracks: TrackResult[];
  albums: AlbumResult[];
}

export interface ProblemIssue {
  location: string;
  message: string;
}

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  code: string;
  request_id: string;
  errors?: ProblemIssue[];
}

export type JobState =
  | "queued"
  | "starting"
  | "running"
  | "cancelling"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface QueueJob {
  id: string;
  url: string;
  title: string;
  artist: string;
  state: JobState;
  status_message: string;
  progress_phase?: string;
  progress_percent?: number;
  attempt_count: number;
  last_error?: string;
  output_path?: string;
  source_import_id?: string;
  source_occurrence_id?: string;
  source_playlist_title?: string;
  created_at: number;
  updated_at: number;
  started_at?: number;
  completed_at?: number;
}

export interface QueueCounts {
  queued: number;
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
  interrupted: number;
}

export interface QueueSnapshot {
  jobs: QueueJob[];
  counts: QueueCounts;
}

export interface EnqueueInput {
  url: string;
  title: string;
  artist: string;
}

export interface EnqueueResponse {
  job: QueueJob;
  duplicate: boolean;
}

export interface BatchEnqueueResponse {
  added: number;
  duplicates: number;
  skipped_library: number;
  invalid: number;
}

export interface NowPlayingTrack {
  title: string;
  artist: string;
  track_id?: string;
}

export interface NowPlayingResponse {
  available: boolean;
  track?: NowPlayingTrack;
  player?: string;
  reason?: string;
}

export type ImportStatus =
  | "extracting"
  | "matching"
  | "paused"
  | "matching_complete";

export type MatchingStatus =
  | "pending"
  | "searching"
  | "candidates_ready"
  | "no_results"
  | "failed";

export type ReviewStatus = "unreviewed" | "selected" | "skipped";

export type ImportQueueOutcome =
  | "none"
  | "queued"
  | "duplicate"
  | "skipped_library";

export interface ImportCounts {
  total: number;
  pending: number;
  searching: number;
  matched: number;
  no_results: number;
  failed: number;
  selected: number;
  queued: number;
  duplicate: number;
  skipped: number;
  library_skipped: number;
  unresolved: number;
}

export interface AmazonCandidate {
  id: string;
  url: string;
  track_key: string;
  title: string;
  artist: string;
  album: string;
  duration_seconds?: number | null;
  artwork_url?: string | null;
  provider_position: number;
  rank: number;
  score: number;
  explanation: string;
}

export interface ImportSourceTrack {
  id: string;
  position: number;
  spotify_track_id?: string | null;
  source_url?: string | null;
  title: string;
  artist: string;
  duration_seconds?: number | null;
  matching_status: MatchingStatus;
  review_status: ReviewStatus;
  selected_candidate_id?: string | null;
  library_match?: LibraryMatch | null;
  queue_outcome: ImportQueueOutcome;
  queued_job_id?: string | null;
  source_duplicate_of_id?: string | null;
  queued_duplicate_of_source_id?: string | null;
  attempt_count: number;
  last_error?: string | null;
  candidates: AmazonCandidate[];
}

export interface ImportSession {
  id: string;
  source_url: string;
  spotify_type?: "album" | "playlist" | null;
  spotify_id?: string | null;
  title: string;
  artwork_url?: string | null;
  status: ImportStatus;
  revision: number;
  counts: ImportCounts;
  last_error?: string | null;
  created_at: number;
  updated_at: number;
  matching_started_at?: number | null;
  matching_completed_at?: number | null;
}

export interface ImportSessionDetail extends ImportSession {
  sources: ImportSourceTrack[];
}

export interface ImportListResponse {
  imports: ImportSession[];
}

export interface ImportEnqueueResponse {
  session: ImportSessionDetail;
  queued: number;
  duplicate: number;
  skipped_library: number;
}
