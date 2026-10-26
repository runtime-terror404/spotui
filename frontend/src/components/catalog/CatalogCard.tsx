import type { CatalogItem } from "../../api/types";
import { kindLabel } from "../../features/catalog/labels";
import { Artwork } from "../ui/Artwork";

interface CatalogCardProps {
  item: CatalogItem;
  onOpen: (url: string) => void;
}

export function CatalogCard({ item, onOpen }: CatalogCardProps) {
  const artist = item.kind === "artist";

  return (
    <button
      type="button"
      className={`catalog-card catalog-card--${artist ? "artist" : "square"}`}
      onClick={() => onOpen(item.url)}
      aria-label={`Open ${kindLabel(item.kind)} ${item.title}`}
    >
      <Artwork
        src={item.image}
        alt=""
        shape={artist ? "circle" : "square"}
        className="catalog-card__art"
      />
      <span className="catalog-card__body">
        <span className="catalog-card__title" title={item.title}>
          {item.title}
        </span>
        {item.subtitle ? (
          <span className="catalog-card__subtitle" title={item.subtitle}>
            {item.subtitle}
          </span>
        ) : null}
        {item.in_library ? (
          <span className="library-badge">In library</span>
        ) : null}
      </span>
    </button>
  );
}
