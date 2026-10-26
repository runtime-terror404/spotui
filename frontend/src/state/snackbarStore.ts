import { create } from "zustand";

export type SnackbarTone = "info" | "success" | "error";

export interface SnackbarMessage {
  id: number;
  message: string;
  tone: SnackbarTone;
}

interface SnackbarState {
  messages: SnackbarMessage[];
  push: (message: string, tone?: SnackbarTone) => void;
  dismiss: (id: number) => void;
  reset: () => void;
}

let nextId = 1;

export const useSnackbarStore = create<SnackbarState>((set) => ({
  messages: [],
  push: (message, tone = "info") =>
    set((state) => ({
      messages: [...state.messages.slice(-2), { id: nextId++, message, tone }],
    })),
  dismiss: (id) =>
    set((state) => ({
      messages: state.messages.filter((message) => message.id !== id),
    })),
  reset: () => set({ messages: [] }),
}));
