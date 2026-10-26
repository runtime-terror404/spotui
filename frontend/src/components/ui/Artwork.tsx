import { useEffect, useState } from "react";

import { MusicIcon } from "../icons";

interface ArtworkProps {
  src?: string;
  alt: string;
  shape?: "square" | "circle";
  className?: string;
}

export function Artwork({
  src,
  alt,
  shape = "square",
  className = "",
}: ArtworkProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  const classes = `artwork artwork--${shape} ${className}`.trim();

  if (!src || failed) {
    return (
      <div className={`${classes} artwork--fallback`} aria-hidden="true">
        <MusicIcon />
      </div>
    );
  }

  return (
    <img
      className={classes}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
