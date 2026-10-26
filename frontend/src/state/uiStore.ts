import { create } from "zustand";

export type AppView = "search" | "detail" | "queue";

interface UIState {
  view: AppView;
  inputQuery: string;
  submittedQuery: string;
  detailUrl: string | null;
  searchScrollY: number;
  setInputQuery: (query: string) => void;
  submitSearch: (query: string) => void;
  openDetail: (url: string) => void;
  setSearchScrollY: (offset: number) => void;
  backToSearch: () => void;
  openSearch: () => void;
  openQueue: () => void;
  reset: () => void;
}

const initialState = {
  view: "search" as AppView,
  inputQuery: "",
  submittedQuery: "",
  detailUrl: null,
  searchScrollY: 0,
};

export const useUIStore = create<UIState>((set) => ({
  ...initialState,
  setInputQuery: (inputQuery) => set({ inputQuery }),
  submitSearch: (query) => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    set({
      view: "search",
      inputQuery: trimmed,
      submittedQuery: trimmed,
      detailUrl: null,
      searchScrollY: 0,
    });
  },
  openDetail: (detailUrl) => set({ view: "detail", detailUrl }),
  setSearchScrollY: (searchScrollY) => set({ searchScrollY }),
  backToSearch: () => set({ view: "search", detailUrl: null }),
  openSearch: () => set({ view: "search", detailUrl: null }),
  openQueue: () => set({ view: "queue" }),
  reset: () => set(initialState),
}));
