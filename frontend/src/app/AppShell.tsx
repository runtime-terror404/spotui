import { MobileNav } from "../components/layout/MobileNav";
import { NavRail } from "../components/layout/NavRail";
import { SearchHeader } from "../components/layout/SearchHeader";
import { SnackbarRegion } from "../components/ui/SnackbarRegion";
import { EntityDetailView } from "../features/entity-details/EntityDetailView";
import { ImportsPage } from "../features/imports/ImportsPage";
import { QueuePage } from "../features/queue/QueuePage";
import { QueuePanel } from "../features/queue/QueuePanel";
import { SearchView } from "../features/search/SearchView";
import { SettingsPage } from "../features/settings/SettingsPage";
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
            {view === "queue" ? <QueuePage /> : null}
            {view === "imports" ? <ImportsPage /> : null}
            {view === "settings" ? <SettingsPage /> : null}
            {view === "detail" && detailUrl ? (
              <EntityDetailView url={detailUrl} />
            ) : null}
            {view === "search" ? <SearchView /> : null}
          </main>
        </div>
        <QueuePanel />
      </div>
      <MobileNav />
      <SnackbarRegion />
    </>
  );
}
