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
