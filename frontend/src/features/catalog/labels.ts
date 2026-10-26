import type { CatalogKind } from "../../api/types";

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
