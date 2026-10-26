import { useEffect } from "react";

import { useUIStore } from "../state/uiStore";
import { AppShell } from "./AppShell";

export function App() {
  const view = useUIStore((state) => state.view);
  const detailUrl = useUIStore((state) => state.detailUrl);
  const searchScrollY = useUIStore((state) => state.searchScrollY);

  useEffect(() => {
    if (view !== "search") {
      window.scrollTo({ top: 0, behavior: "auto" });
      return;
    }
    const scrollY = searchScrollY;
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: scrollY, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [view, detailUrl, searchScrollY]);

  return <AppShell />;
}
