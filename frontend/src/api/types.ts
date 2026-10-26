export type CatalogKind =
  | "artist"
  | "album"
  | "track"
  | "playlist"
  | "community_playlist";

export interface CatalogItem {
  title: string;
  subtitle: string;
  url: string;
  kind: CatalogKind;
  image?: string;
  in_library?: boolean;
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
  in_library?: boolean;
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
