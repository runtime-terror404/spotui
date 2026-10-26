import { useUIStore } from "../../state/uiStore";
import { QueueIcon, SearchIcon, SettingsIcon } from "../icons";

export function MobileNav() {
  const view = useUIStore((state) => state.view);
  const openSearch = useUIStore((state) => state.openSearch);
  const openQueue = useUIStore((state) => state.openQueue);
  const setSearchScrollY = useUIStore((state) => state.setSearchScrollY);

  return (
    <nav className="mobile-nav" aria-label="Primary mobile">
      <button
        type="button"
        className="mobile-nav__item"
        aria-current={view !== "queue" ? "page" : undefined}
        onClick={openSearch}
      >
        <SearchIcon />
        <span>Search</span>
      </button>
      <button
        type="button"
        className="mobile-nav__item"
        aria-current={view === "queue" ? "page" : undefined}
        onClick={() => {
          if (view === "search") {
            setSearchScrollY(window.scrollY);
          }
          openQueue();
        }}
      >
        <QueueIcon />
        <span>Queue</span>
      </button>
      <button
        type="button"
        className="mobile-nav__item"
        disabled
        aria-label="Settings, not available yet"
      >
        <SettingsIcon />
        <span>Settings</span>
      </button>
    </nav>
  );
}
