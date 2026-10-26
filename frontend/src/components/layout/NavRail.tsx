import { QueueIcon, SearchIcon, SettingsIcon } from "../icons";

export function NavRail() {
  return (
    <nav className="nav-rail" aria-label="Primary">
      <div className="nav-rail__brand" aria-label="SpotUI" title="SpotUI">
        S
      </div>
      <ul className="nav-rail__items">
        <li>
          <button
            type="button"
            className="nav-item is-active"
            aria-current="page"
            aria-label="Search"
          >
            <SearchIcon />
            <span>Search</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="nav-item"
            disabled
            aria-label="Queue, not available yet"
            title="Queue is not available yet"
          >
            <QueueIcon />
            <span>Queue</span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="nav-item"
            disabled
            aria-label="Settings, not available yet"
            title="Settings are not available yet"
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
