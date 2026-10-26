import { NavRail } from "../components/layout/NavRail";
import { SearchHeader } from "../components/layout/SearchHeader";
import { EntityDetailView } from "../features/entity-details/EntityDetailView";
import { SearchView } from "../features/search/SearchView";
import { useUIStore } from "../state/uiStore";

export function AppShell() {
  const view = useUIStore((state) => state.view);
  const detailUrl = useUIStore((state) => state.detailUrl);

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="app-shell">
        <NavRail />
        <div className="workspace">
          <SearchHeader />
          <main id="main-content" className="workspace__main" tabIndex={-1}>
            {view === "detail" && detailUrl ? (
              <EntityDetailView url={detailUrl} />
            ) : (
              <SearchView />
            )}
          </main>
        </div>
      </div>
    </>
  );
}
