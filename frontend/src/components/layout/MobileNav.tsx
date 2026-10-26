import { useUIStore } from "../../state/uiStore";
import { ImportsIcon, QueueIcon, SearchIcon, SettingsIcon } from "../icons";

export function MobileNav() {
  const view = useUIStore((state) => state.view);
  const openSearch = useUIStore((state) => state.openSearch);
  const openQueue = useUIStore((state) => state.openQueue);
  const openImports = useUIStore((state) => state.openImports);
  const openSettings = useUIStore((state) => state.openSettings);
  const setSearchScrollY = useUIStore((state) => state.setSearchScrollY);
  const searchActive = view === "search" || view === "detail";

  return (
    <nav className="mobile-nav" aria-label="Primary mobile">
      <button
        type="button"
        className="mobile-nav__item"
        aria-current={searchActive ? "page" : undefined}
        onClick={openSearch}
      >
        <SearchIcon />
        <span>Search</span>
      </button>
      <button
        type="button"
        className="mobile-nav__item"
        aria-current={view === "imports" ? "page" : undefined}
        onClick={() => openImports()}
      >
        <ImportsIcon />
        <span>Imports</span>
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
        aria-current={view === "settings" ? "page" : undefined}
        onClick={openSettings}
      >
        <SettingsIcon />
        <span>Settings</span>
      </button>
    </nav>
  );
}
