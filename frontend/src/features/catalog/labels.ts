import type { CatalogKind, LibraryMatch } from "../../api/types";

export function kindLabel(kind: CatalogKind): string {
  switch (kind) {
    case "artist":
      return "Artist";
    case "album":
      return "Album";
    case "playlist":
      return "Playlist";
    case "community_playlist":
      return "Community playlist";
    case "track":
      return "Track";
  }
}

export function isDetailKind(kind: CatalogKind): boolean {
  return kind !== "track";
}

export function libraryMatchLabel(match?: LibraryMatch | null): string {
  if (match === "exact") {
    return "Exact match in your library";
  }
  if (match === "likely") {
    return "Likely match in your library";
  }
  return "In your library";
}
