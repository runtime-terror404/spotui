import { useUIStore } from "../../state/uiStore";
import { ImportsIcon, QueueIcon, SearchIcon, SettingsIcon } from "../icons";

export function NavRail() {
  const view = useUIStore((state) => state.view);
  const openSearch = useUIStore((state) => state.openSearch);
  const openQueue = useUIStore((state) => state.openQueue);
  const openImports = useUIStore((state) => state.openImports);
  const openSettings = useUIStore((state) => state.openSettings);
  const setSearchScrollY = useUIStore((state) => state.setSearchScrollY);
  const searchActive = view === "search" || view === "detail";

  return (
    <nav className="nav-rail" aria-label="Primary">
      <button
        type="button"
        className="nav-rail__brand"
        aria-label="SpotUI search"
        title="SpotUI"
        onClick={openSearch}
      >
        S
      </button>
      <ul className="nav-rail__items">
        <li>
          <button
            type="button"
            className={`nav-item ${searchActive ? "is-active" : ""}`.trim()}
            aria-current={searchActive ? "page" : undefined}
            aria-label="Search"
            onClick={openSearch}
          >
            <SearchIcon />
            <span>Search</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className={`nav-item ${view === "imports" ? "is-active" : ""}`.trim()}
            aria-current={view === "imports" ? "page" : undefined}
            aria-label="Imports"
            onClick={() => openImports()}
          >
            <ImportsIcon />
            <span>Imports</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className={`nav-item ${view === "queue" ? "is-active" : ""}`.trim()}
            aria-current={view === "queue" ? "page" : undefined}
            aria-label="Queue"
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
        </li>
        <li>
          <button
            type="button"
            className={`nav-item ${view === "settings" ? "is-active" : ""}`.trim()}
            aria-current={view === "settings" ? "page" : undefined}
            aria-label="Settings"
            onClick={openSettings}
          >
            <SettingsIcon />
            <span>Settings</span>
          </button>
        </li>
      </ul>
      <div className="nav-rail__footer">
        <span className="nav-rail__dot" aria-hidden="true" />
        Local
      </div>
    </nav>
  );
}
