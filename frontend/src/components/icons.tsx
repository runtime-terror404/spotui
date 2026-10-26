import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function baseProps(props: IconProps): IconProps {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </svg>
  );
}

export function QueueIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 7h10M4 12h10M4 17h6" />
      <path d="m15 16 2 2 4-5" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.09A1.7 1.7 0 0 0 9 19.35a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.07 14H3v-4h.09A1.7 1.7 0 0 0 4.65 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.07V3h4v.09A1.7 1.7 0 0 0 15 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9 1.7 1.7 0 0 0 20.93 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z" />
    </svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

export function MusicIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M9 18V5l10-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="16" cy="16" r="3" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 3 2.5 20h19L12 3Z" />
      <path d="M12 9v5M12 17.5v.01" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}
