import { useEffect, useRef } from "react";

import logoUrl from "../../assets/logo.png";
import { useUIStore } from "../../state/uiStore";
import { CloseIcon, SearchIcon } from "../icons";
import { Button } from "../ui/Button";
import { NowPlayingButton } from "./NowPlayingButton";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    target.isContentEditable
  );
}

export function SearchHeader() {
  const inputQuery = useUIStore((state) => state.inputQuery);
  const setInputQuery = useUIStore((state) => state.setInputQuery);
  const submitSearch = useUIStore((state) => state.submitSearch);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "/" ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        isEditableTarget(event.target)
      ) {
        return;
      }
      event.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const trimmed = inputQuery.trim();

  return (
    <header className="app-header">
      <span className="mobile-brand">
        <img className="brand-mark" src={logoUrl} alt="" />
        SpotUI
      </span>
      <form
        className="search-form"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (!trimmed) {
            return;
          }
          submitSearch(trimmed);
          window.scrollTo({ top: 0, behavior: "auto" });
        }}
      >
        <span className="search-form__icon" aria-hidden="true">
          <SearchIcon />
        </span>
        <input
          ref={inputRef}
          type="search"
          value={inputQuery}
          onChange={(event) => setInputQuery(event.target.value)}
          placeholder="Search Amazon Music"
          aria-label="Search Amazon Music"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
        />
        {inputQuery ? (
          <button
            type="button"
            className="search-form__clear"
            aria-label="Clear search"
            onClick={() => {
              setInputQuery("");
              inputRef.current?.focus();
            }}
          >
            <CloseIcon />
          </button>
        ) : (
          <kbd className="search-form__hint" aria-hidden="true">
            /
          </kbd>
        )}
        <Button
          type="submit"
          variant="primary"
          className="search-form__submit"
          disabled={!trimmed}
        >
          Search
        </Button>
      </form>
      <NowPlayingButton />
    </header>
  );
}
