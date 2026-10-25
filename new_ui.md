# SpotUI Web UI Design Specification

**Status:** Design decisions finalized. Implementation specification for the SpotUI web interface overhaul.

**Primary file:** `spotui_ui.html`

**Related implementation:** `spotui.py`, which serves the page and provides the local HTTP API.

## 1. Product direction

Redesign SpotUI as a clean, desktop-first music search and download utility using a restrained frosted-glass treatment and Material 3 inspired components.

The interface should feel like a focused desktop application, not a generic streaming-service clone. Amazon Music search and reliable download management remain the core workflows. The visual refresh must not change track selection, library matching, download resolution, queue persistence, or other existing business logic unless a separately agreed backend change is required.

### Design principles

1. **Readable before decorative.** Use solid surfaces for search results, album cards, track rows, queue entries, and settings. Restrict glass and blur to selected chrome elements.
2. **Material 3 inspired, not dependent on Material Web.** Use a consistent token system, tonal surfaces, clear component states, soft corners, and accessible contrast. Do not introduce a large UI framework solely for styling.
3. **Desktop-first, responsive by design.** Keep the three-zone shell on wide screens. Reflow it deliberately on tablets and phones rather than shrinking desktop columns until they become unusable.
4. **Persistent operational context.** Preserve navigation and the compact queue while the user searches or inspects album and artist details.
5. **Real state only.** The UI must reflect the server's actual API data. Do not show fabricated percentages, fake history, pretend server health, or unsupported action buttons.
6. **Motion has a purpose.** Use brief Material-style transitions for view changes and overlays. Respect reduced-motion preferences.
7. **Keep the interface fast.** Prefer CSS, inline SVG icons, and browser-native capabilities. Avoid heavy animation, continuous blur over large areas, and unnecessary new dependencies.

## 2. Scope

### Included

- New application shell with left navigation, central workspace, and compact right queue panel on desktop.
- Light and dark themes that follow the operating-system preference by default.
- Lavender and periwinkle accent palette.
- Persistent global search header on Search and detail views.
- Search shortcut, Enter-to-search, and Now Playing search action.
- Categorized search results for artists, albums, tracks, and any additional result categories the API returns.
- Dedicated artist and album detail views.
- Compact queue overview plus a full Queue workspace.
- Responsive tablet and phone navigation.
- Minimal Settings for theme, optional accent selection, reduced motion, and basic app/server information.
- Loading, empty, error, success, and failure states.
- Keyboard, contrast, focus, and reduced-motion requirements.

### Not included in the visual redesign alone

- Changes to Amazon Music search or track selection logic.
- Changes to `lucida` download behavior or download quality handling.
- New download sources or music providers.
- New queue capabilities presented as working controls before the backend supports them.
- A frontend framework migration.
- A custom user-defined arbitrary color picker. Use predefined accent choices if the accent picker is implemented.

## 3. Information architecture

The primary navigation has three destinations:

- **Search.** Search Amazon Music, review categorized results, and open artist, album, or playlist details.
- **Queue.** Manage active and waiting downloads, retry failures, cancel queued jobs, and access queue history once the backend exposes that capability.
- **Settings.** Configure interface preferences and view basic application/server information.

The global header remains available across all destinations. On Search and detail views, show the full search field. On Queue and Settings, keep the header but reduce the search field's visual emphasis so it does not compete with the active workspace.

### Main workflows

1. Enter a search term, press Enter or select Search, and review results grouped by type.
2. Select an artist or album to open a dedicated detail page in the central workspace.
3. Use a track download action or a detail-page bulk action to add supported tracks to the queue.
4. Inspect the compact right queue panel while browsing. Select Queue to open the full queue manager in the central workspace.
5. Use the Now Playing action to read local MPRIS metadata, put the current track title into the search field, and submit that title as a search.
6. Use Settings to change browser-local appearance and accessibility preferences.

## 4. Application shell

### Wide desktop layout

Use a full-height three-zone layout below the application header:

```text
+----------+------------------------------------------+----------------------+
| Left nav | Global header and central workspace      | Compact queue        |
|          | Search / results / artist or album       | Active + recent jobs |
| Search   | detail / full queue manager / settings   | Queue counts         |
| Queue    |                                          |                      |
| Settings |                                          |                      |
+----------+------------------------------------------+----------------------+
```

Recommended initial dimensions:

- Left navigation rail: 72 to 80 px wide.
- Right queue panel: 300 to 340 px wide.
- Main workspace: flexible, with `min-width: 0` and vertical scrolling.
- Main inter-zone gap: 16 to 24 px depending on available width.
- Application content padding: 20 to 28 px on desktop.
- Header height: target 72 to 88 px, including vertical padding.

Use a 3-column CSS grid or an equivalent layout with the left rail and queue widths defined by tokens. Do not center the app inside a fixed 1180 px shell when that would waste a wide monitor's available space. Retain a readable maximum width for individual result grids and long text, not for the whole application shell.

The right queue panel stays visible on desktop while the central workspace switches between Search, detail, Queue, and Settings.

### Navigation rail

- Use a compact SpotUI wordmark or icon at the top.
- Provide Search, Queue, and Settings destinations.
- Each destination uses a recognizable icon and a text label or tooltip.
- Show selected navigation with a lavender tonal background and clear icon/text contrast.
- Use `aria-current="page"` on the selected navigation link or button.
- Show a small queue count only when it adds useful information. Do not let a badge dominate the rail.
- Keep focus order logical and ensure the rail works entirely with a keyboard.

### Global header

On Search and detail views, the header contains:

- The persistent search input.
- A clearly labeled Search submit button or an equivalent explicit submit control.
- A visible `/` shortcut hint when space permits.
- A compact Now Playing search action.
- A small current-track label when MPRIS data is available, without forcing a long title into the header.

On Queue and Settings, preserve the header and provide access to search, but reduce the search field's width or prominence. Do not let search look like the active content on those pages.

Use a slightly translucent header surface only when it sits above scrolling content. Keep its text and controls on a sufficiently opaque background for contrast. If the browser does not support `backdrop-filter`, fall back to a solid surface token.

## 5. Responsive behavior

Use layout breakpoints as a starting point, then test the real rendered layout with the three-zone content and long titles. Avoid tying breakpoints only to a specific device label.

### Desktop, approximately 1200 px and wider

- Show the left navigation rail, central workspace, and persistent right queue panel.
- Show the full global search field on Search and detail views.
- Keep the queue panel compact, showing the active job, a few recent jobs, counts, and statuses.
- Selecting Queue replaces the central workspace with the full queue manager. The right overview remains visible.

### Tablet, approximately 760 to 1199 px

- Collapse the navigation rail to icons if it does not already use icons only.
- Hide the persistent queue column and expose the compact queue in a side drawer or panel opened from the header or queue affordance.
- Keep a central workspace wide enough for album cards and track metadata.
- Allow the search field to shrink while keeping Search and Now Playing controls reachable.
- Close the queue drawer with its close control, Escape, and an outside click when safe to do so.

### Phone, below approximately 760 px

- Replace the left rail with a bottom navigation bar containing Search, Queue, and Settings.
- Keep the global search field visible on Search and detail views. In Queue and Settings, keep search accessible without taking over the page header.
- Open Queue as a frosted bottom sheet above the page content. Include a visible drag handle, a close button, and an accessible name. A close button must remain available even when drag gestures are supported.
- Use one main content column.
- Use adaptive album grids, typically two columns on narrow phones and more columns as width allows.
- Keep track rows compact, but preserve readable titles and adequately sized download actions.
- Reserve padding for the bottom navigation and safe areas so the last result is not obscured.
- Bottom sheets must cap their height relative to the viewport and scroll internally when the queue is long.

### Very narrow screens

- Allow the Search field and submit action to wrap or stack without horizontal page scrolling.
- Do not truncate the only copy of a track's failure message. Provide a details expansion or full queue view when needed.
- Keep primary actions reachable at small widths. Icon-only actions require accessible labels and a clear focus state.

## 6. Color system

Use a lavender/periwinkle seed with coordinated light and dark token sets. Treat these values as an initial palette. Check contrast in the implemented UI before final release.

### Light theme

| Token | Initial value | Usage |
|---|---|---|
| `--color-background` | `#F8F7FC` | Main app background |
| `--color-surface` | `#FFFBFF` | Cards and primary content surfaces |
| `--color-surface-low` | `#F5F2FA` | Subtle section backgrounds |
| `--color-surface-container` | `#F0ECF5` | Secondary containers and navigation hover |
| `--color-surface-high` | `#E8E3F0` | Raised or selected neutral surfaces |
| `--color-text` | `#1C1B22` | Primary text |
| `--color-text-secondary` | `#48454F` | Supporting text and metadata |
| `--color-outline` | `#797582` | Borders and control outlines, not low-contrast body text |
| `--color-primary` | `#62518C` | Primary buttons, focus, selected controls |
| `--color-on-primary` | `#FFFFFF` | Text/icons on primary fills |
| `--color-primary-container` | `#E9DDFF` | Soft selected states and tonal surfaces |
| `--color-on-primary-container` | `#24143B` | Text/icons on primary containers |
| `--color-success` | `#236B45` | Success status, paired with text/icon |
| `--color-error` | `#BA1A1A` | Error status and destructive emphasis |
| `--color-warning` | `#805600` | Warning status, paired with text/icon |

### Dark theme

| Token | Initial value | Usage |
|---|---|---|
| `--color-background` | `#141218` | Main app background |
| `--color-surface` | `#1C1A22` | Cards and primary content surfaces |
| `--color-surface-low` | `#19171F` | Subtle recessed surfaces |
| `--color-surface-container` | `#24212C` | Secondary containers and navigation |
| `--color-surface-high` | `#302C38` | Raised or selected neutral surfaces |
| `--color-text` | `#E7E0EB` | Primary text |
| `--color-text-secondary` | `#CAC4D0` | Supporting text and metadata |
| `--color-outline` | `#938D9B` | Borders and control outlines |
| `--color-primary` | `#D0BCFF` | Primary actions and focus accents |
| `--color-on-primary` | `#381E72` | Text/icons on primary fills |
| `--color-primary-container` | `#4F3785` | Selected tonal surfaces |
| `--color-on-primary-container` | `#EADDFF` | Text/icons on primary containers |
| `--color-success` | `#8ED6A8` | Success status, paired with text/icon |
| `--color-error` | `#FFB4AB` | Error status and destructive emphasis |
| `--color-warning` | `#F2C078` | Warning status, paired with text/icon |

### Color rules

- Use lavender/periwinkle for primary actions, selected navigation, keyboard focus, progress/status emphasis, and active controls.
- Keep most content backgrounds neutral. Do not tint every card purple.
- Use semantic success, warning, and error colors only for the matching state. Never communicate status through color alone.
- Avoid gradients as a default card background. A very subtle ambient background tint is acceptable if it does not reduce contrast or cause visual noise.
- Define colors through CSS custom properties. Components should not hard-code color values outside the token definitions.
- Use `color-scheme` and native form control styling as appropriate for the active theme.
- Verify text and controls against WCAG AA targets. Aim for at least 4.5:1 contrast for ordinary text and 3:1 for large text and meaningful UI boundaries.

## 7. Frosted-glass treatment

Glass is a supporting material, not the primary surface for all content.

### Use subtle frost for

- The top app bar when content scrolls behind it.
- The phone bottom navigation bar.
- The phone queue bottom sheet and tablet queue drawer.
- Small floating elements that need separation from content.

### Use solid surfaces for

- Artist and album cards.
- Track rows and track lists.
- Search-result sections.
- Download job rows and error details.
- Settings groups and form controls.
- Main detail content.

### Frost implementation guidance

- Start with a surface color at approximately 82 to 94 percent opacity, adjusted for the active theme.
- Use modest blur, approximately 10 to 16 px, for small chrome surfaces. Do not put expensive blur on every list row or card.
- Add a thin, low-contrast border to define the edge.
- Use a restrained shadow only when a surface floats above other content.
- Provide a solid surface fallback with `@supports not (backdrop-filter: blur(1px))` or the equivalent feature check.
- Keep text contrast valid after the material is layered over arbitrary content.
- Avoid animated blur, persistent noise textures, bright glass outlines, and large reflective gradients.

## 8. Shape, spacing, and elevation

### Corner radii

| Component | Radius |
|---|---:|
| Result card | 12 px |
| Track row | 10 to 12 px |
| Main panel | 14 to 16 px |
| Dialog or bottom sheet | 16 px, with larger top corners on phone sheets if needed |
| Text field and standard button | 10 to 12 px |
| Small icon button | 8 to 10 px |
| Filter chip or compact status pill | Fully rounded |
| Artist artwork | 50 percent / circle |
| Album artwork | 8 to 12 px |

Do not make every button pill-shaped. Reserve pill geometry for chips, counts, and controls whose shape communicates a compact selection state.

### Spacing scale

Use a 4 px base spacing scale:

- 4 px: tight icon-to-label gaps.
- 8 px: compact row spacing.
- 12 px: card padding and common control gaps.
- 16 px: standard section and panel spacing.
- 24 px: separation between major sections.
- 32 px: large page-level separation where content needs it.

Prefer consistent spacing tokens over one-off margins. Track rows should stay compact, while major album/artist details receive more breathing room.

### Borders and elevation

- Prefer tonal surface separation and a thin outline over stacked shadows.
- Use one restrained shadow level for drawers, bottom sheets, and floating menus.
- Avoid heavy shadows around every card.
- Define border and shadow tokens centrally.

## 9. Typography

Use a Material 3 style type hierarchy with Roboto where available, followed by compatible system sans-serif fonts. Avoid requiring a remote font download for the core interface. The current Fraunces display font and Archivo body font pairing should be removed from the redesigned shell.

Suggested stack:

```css
font-family: Roboto, "Segoe UI", system-ui, -apple-system, sans-serif;
```

### Suggested type scale

| Role | Size | Weight | Notes |
|---|---:|---:|---|
| Page/display title | 28 to 32 px | 600 | Use for a main page or prominent artist/album title |
| Workspace heading | 22 to 24 px | 600 | Use for major view headings |
| Section heading | 18 to 20 px | 600 | Artists, Albums, Tracks, Queue sections |
| Card/track primary text | 14 to 16 px | 500 to 600 | Keep titles readable and single-line where practical |
| Body text | 14 px | 400 | Main explanatory text |
| Metadata and secondary labels | 12 to 13 px | 400 to 500 | Supporting details, not primary messages |
| Compact status/count labels | 12 px minimum target | 500 | Do not rely on tiny all-caps text for important states |

Use sentence case for headings and labels. Avoid excessive letter spacing and uppercase section labels. Truncate long titles with an ellipsis only when the full title remains available through a detail view, tooltip, or accessible label.

## 10. Search workspace

### Search field behavior

- Keep the search input visible in the global header on Search and detail views.
- Submit on Enter and through an explicit Search button.
- Use `/` to focus the search input when focus is not already in an editable field and no modal or sheet is capturing input.
- Do not intercept `/` while the user is typing in an input, textarea, or content-editable area.
- Keep the current query and the last successful search results when opening and closing a detail view.
- Show a clear loading state while search is running. Prevent accidental duplicate submits while the request is in flight, but keep the input editable if the design permits safe cancellation or replacement.
- On failure, show a persistent in-workspace error state with a retry path. A snackbar may repeat the brief summary, but it must not be the only error record.
- When search returns no matches, show a purposeful empty state with the query available and a clear way to edit it.

### Now Playing action

- Use the existing `GET /api/now` MPRIS integration.
- Clicking Now Playing retrieves the current title and artist, places the title in the global search field, and submits a search.
- Show a compact current-track indicator when metadata is available.
- If nothing is playing or MPRIS is unavailable, show a concise error snackbar and leave the user able to search manually.
- Do not add a player, playback controls, or a persistent equalizer animation. SpotUI searches for the current track; it is not the media player.

### Categorized results

Use one scrollable Search page with distinct sections. Preserve all result categories returned by `/api/search`.

- **Artists:** circular artwork, artist name, and useful subtitle/metadata.
- **Albums:** square album artwork, album title, and artist/year metadata where returned.
- **Tracks:** compact horizontal rows with thumbnail, title, artist, library status, and a clear download action.
- **Playlists and community playlists:** show distinct sections when the API returns them. Do not drop categories the current backend supports just because Artists, Albums, and Tracks are the primary visual categories.

Section rules:

- Put the section title and result count at the top of each group.
- Use a responsive `auto-fit` or `auto-fill` grid with a sensible minimum card width. The actual number of columns must follow the available central workspace width, not the whole browser width.
- Keep album cards at balanced density. Use medium artwork and moderate gaps.
- Make artist artwork circular. Make album and playlist artwork square with softly rounded corners.
- Cards open their supported detail view. Track download actions enqueue the selected exact result.
- Preserve the `IN LIBRARY` indicator and the library skip behavior. Ensure the label is readable and does not depend only on green color.
- Provide lazy image loading and a stable fallback for missing artwork.
- Use a skeleton or compact loading indicator for pending search results. Respect reduced motion.

### Empty state

The initial Search state should briefly explain the primary action, for example: “Search Amazon Music for an artist, album, or song.” Keep artwork decoration subtle and static when reduced motion is enabled. Do not make the empty state taller than needed on smaller screens.

## 11. Artist and album detail view

Selecting an artist, album, or supported playlist replaces the central Search results with a dedicated detail view. Keep the left navigation and desktop queue panel visible.

### Detail header

- Provide a Back control and a clear return-to-search path. A breadcrumb such as `Search / Album title` is optional if it improves orientation.
- Restore the last search query, results, and scroll position when returning from details.
- Use a large square album or playlist image. Use circular artwork for artists.
- Show the content type, title, artist/creator and other metadata returned by the API.
- Place the primary bulk action in the header: `Download all (N)` for albums/playlists or `Download top tracks (N)` for artists, consistent with current backend behavior.
- Show library counts/notes only when the server returns sufficient data. Do not invent track availability or metadata.
- On a narrow screen, stack the artwork and metadata cleanly rather than compressing the heading.

### Detail content

- Artist detail: Albums section where returned, followed by Top tracks.
- Album detail: Tracks section.
- Playlist detail: the track list returned by the existing resolver.
- Use the same track-row component and library status across Search and detail pages.
- Provide a download action per track, and a bulk-download action when supported.
- Track rows should keep the title, artist, and download action aligned without horizontal page scrolling.
- Preserve proper disabled/queued states after a successful enqueue. Refresh queue state after enqueueing.
- When detail loading fails, show an inline error and a way to return to results or retry.

## 12. Queue design

The queue has two presentations: a compact overview and a full manager.

### Compact desktop queue

Keep this panel present on wide desktop layouts while the central workspace changes.

Show:

- Queue heading and counts for queued and active jobs.
- The active job first.
- A few recent/important jobs, prioritizing active and queued jobs, then failed jobs and other recent statuses.
- Track title, status message, and a restrained status icon.
- Cancel for a queued job and Retry for a failed job, where the current API supports those actions.
- A clear entry point to open the full Queue workspace.

Keep the panel visually quiet. Do not show every historical job in this narrow panel. The panel's list may scroll within a bounded height, but the header and Queue entry point should remain reachable.

### Full Queue workspace

Selecting Queue in the left navigation or phone bottom navigation opens the full manager in the central workspace. On desktop, retain the compact right overview.

The full manager should provide:

- Clear counts for queued, active, failed, completed, and cancelled jobs where those states are available.
- Sections or filters for Active, Waiting, Failed, and History once supported by actual queue data.
- Each job's title, artist if available, current status message, last update or elapsed time where useful, and contextual actions.
- Retry for failed jobs.
- Cancel for queued jobs only, matching the existing API behavior.
- Removal and persistent history only after the backend supports those operations.
- Meaningful empty states for an empty queue and an empty filtered view.
- Inline failure detail and retry actions that remain visible until the failure is resolved or the user dismisses/removes it through a supported operation.

### Queue status presentation

Use text plus an icon, not color alone, for every status.

| Backend status | UI label | Treatment |
|---|---|---|
| `queued` | Queued | Neutral waiting state |
| `running` | Starting / current phase message | Active accent, but no continuous pulse required |
| `downloading` | Downloading / current phase message | Active accent with visible text |
| `failed` | Failed | Error color, failure message, Retry action |
| `done` | Completed / saved | Success color and file name where returned |
| `cancelled` | Cancelled | Neutral secondary state |

The current queue payload exposes statuses and phase messages, but not a reliable numeric percentage. Do not render fake percentage bars. Use an indeterminate progress indicator only while a job is actively running, with a text label such as “Downloading” or the backend-provided phase message.

### Current backend limits that affect Queue UI

The current `spotui.py` implementation provides:

- `GET /api/queue` for queue snapshots.
- `POST /api/cancel` for cancelling queued jobs.
- `POST /api/retry` for retrying failed jobs.
- Persistent queue data at `~/.local/share/spotui/queue.json`.
- A single-worker FIFO queue.
- Server-side pruning of completed jobs after approximately 3 seconds.

The current API does **not** provide a job-removal endpoint, a dedicated historical queue endpoint, or numeric progress values. Failed jobs remain visible, but completed jobs disappear quickly. Therefore:

1. Do not expose a working Remove action until a corresponding endpoint exists.
2. Do not present a persistent History tab populated by client guesses. Add server-side history/retention support first.
3. Do not show percentage completion until the worker reports a trustworthy progress value.
4. Until backend work is complete, keep the full Queue UI limited to the available statuses and supported actions. Mark removal and history as pending integration in implementation notes, not as clickable placeholders.

Recommended backend follow-up before enabling all planned queue controls:

- Add a defined removal operation, including the statuses that are eligible for removal.
- Add an explicit retention/history policy, or return archived jobs through a dedicated endpoint.
- If percentage progress is desired, expose a numeric progress field with documented semantics. Otherwise continue to show phase-based progress.
- Keep queue operations idempotent where feasible and return useful error messages for failed actions.

## 13. Settings

Settings should stay minimal. Do not duplicate queue management or download operations in this view.

### Appearance

- Theme selector: **System**, **Light**, and **Dark**.
- Default to System and follow `prefers-color-scheme`.
- Persist a manual override in browser `localStorage`.
- Restore the operating-system theme when System is selected.
- Default accent is lavender/periwinkle.
- If accent customization is kept in scope, offer a small set of predefined accessible accents. Do not add a large arbitrary color picker. Persist the chosen preset locally and derive its tonal tokens consistently for light and dark modes.

### Accessibility

- Provide a Reduced motion preference.
- Respect `prefers-reduced-motion` automatically by default.
- Let the user explicitly enable reduced motion in Settings and persist that override locally.
- Reduced motion must disable decorative entrance animations, smooth scrolling, animated equalizer bars, and pulsing job dots. Preserve functional status indicators and loading feedback in static form.

### App and server information

- Use `GET /api/health` to show server connectivity.
- The current health API returns `{ "ok": true }` when reachable. It does not return a software version, dependency versions, or detailed diagnostics.
- Show a version only if a version constant or build metadata is explicitly maintained by the project. Do not infer one from a file timestamp.
- Distinguish “Server reachable” from “MPRIS available”. The health endpoint does not validate MPRIS, Amazon search, or the download worker.
- Keep system information factual and brief. Do not add controls for unsupported backend configuration.

### Preference storage

Theme, accent preset, and reduced-motion override are presentation preferences, so browser-local storage is appropriate. Handle unavailable or invalid stored values safely and fall back to System theme and the default lavender accent. Do not store queue contents, track metadata, Amazon results, or sensitive data in local storage as a substitute for the server API.

## 14. Notifications and feedback

Use layered feedback.

### Inline, persistent feedback

Use inline states for:

- Search request failure.
- Detail loading failure.
- Download job failure and its server-provided message.
- A failed retry/cancel operation.
- Connection loss where it affects the active view.

Keep actionable errors in the relevant page or queue job until resolved or deliberately dismissed. A toast is supplemental, not the only record of a failed operation.

### Snackbars

Use compact, transient snackbars for routine confirmations such as:

- Track added to the queue.
- Duplicate track already queued.
- Bulk-add result summary.
- Preference saved, where confirmation adds value.

Use a modest timeout, around 2.8 to 4 seconds, and do not make snackbars block clicks or keyboard interaction. Avoid a snackbar for every queue poll or progress update.

### Dialogs and destructive actions

- Do not use modal dialogs for routine download operations.
- Use inline actions for Retry and Cancel where possible.
- If a future removal action permanently deletes a queue record, provide a clear consequence and either a safe confirmation or a reliable Undo path. Do not create an Undo button unless the backend supports the undo operation.
- Avoid repeated dialogs for ordinary state transitions.

## 15. Motion

Use gentle Material motion with short durations and restrained distance.

Suggested durations:

- Hover, focus, and color changes: 120 to 180 ms.
- Card/state transitions: 160 to 220 ms.
- Detail view transition: 180 to 240 ms with a subtle fade and small directional movement.
- Drawer or bottom sheet: 220 to 280 ms, with no bounce.
- Snackbar entrance/exit: approximately 180 to 220 ms.

Rules:

- Avoid large translations, spring/bounce effects, parallax, or continuous decorative animation.
- Use small directional transitions when moving between Search and a detail view.
- Keep entrance animation subtle and avoid long stagger sequences for large result sets.
- Animate the queue only when its state changes, not every polling cycle.
- Respect `prefers-reduced-motion` and the user's Settings override.
- Under reduced motion, remove non-essential movement and use instant or near-instant state changes. Retain clear status updates.

## 16. Accessibility and interaction standards

- Use semantic landmarks: header, navigation, main, aside where appropriate, and clearly named sections.
- Use real buttons and links instead of clickable `div` elements for interactive controls.
- Every icon-only button needs an accessible name, visible focus indication, and a tooltip or adjacent label when useful.
- Keep keyboard order consistent with the visual order.
- Support `/` to focus Search, Enter to submit, Escape to close an open drawer/sheet, and standard Tab/Shift+Tab navigation.
- Do not hijack keyboard shortcuts while a text field or other editable control has focus.
- Use `aria-live="polite"` for meaningful queue counts and non-urgent state summaries. Use an appropriate alert role for an error that requires immediate awareness, without announcing each poll.
- Provide `aria-expanded`, `aria-controls`, and dialog/sheet semantics for overlays where appropriate.
- Maintain visible focus rings in both themes. Do not remove outlines without providing a clear replacement.
- Never indicate status by color alone. Pair colors with a short label or icon and accessible text.
- Aim for WCAG AA contrast, at least 4.5:1 for normal text and 3:1 for large text and meaningful component boundaries.
- Use a practical touch target of approximately 44 by 44 CSS pixels for primary phone controls. Secondary compact controls should remain easy to activate.
- Ensure browser zoom up to 200 percent does not hide controls or require horizontal scrolling for the primary page flow.
- Give album/artist artwork appropriate alternative text when it conveys identity. Use empty alt text for decorative artwork when the title is already available as adjacent text.
- Do not rely on hover as the only way to reveal essential actions. Touch and keyboard users need equivalent access.

## 17. State and navigation behavior

Maintain one source of truth for current view and query state.

Suggested frontend state:

- `activeView`: `search`, `detail`, `queue`, or `settings`.
- `searchQuery`: current input value.
- `lastSuccessfulQuery`: last query that returned results.
- `lastSearchSections`: last successful categorized results.
- `activeDetail`: selected artist, album, or playlist URL and resolved payload.
- `selectedTheme`: `system`, `light`, or `dark`.
- `selectedAccent`: a supported accent token key, defaulting to lavender/periwinkle.
- `reduceMotionOverride`: `system`, `on`, or `off`, or an equivalent clearly defined boolean model.
- `queueSnapshot`: latest result from `GET /api/queue`.
- `queuePanelOpen`: tablet/phone overlay state.

Behavior requirements:

- Changing `activeView` must not discard Search query/results unless the user explicitly starts a new search.
- Back from detail restores the Search view, query, result list, and scroll location.
- Queue polling updates the compact panel and full Queue view from the same queue snapshot.
- Queue polling must not re-create every DOM node on each poll or restart animations for unchanged jobs. Keep keyed reconciliation or an equivalent stable rendering strategy.
- Failed API requests must not wipe the last successful Search result list unless the failure is for that exact active search and the UI explains what happened.
- Store only view preferences locally. Treat the server API as the source of truth for queue data and library matching.

## 18. Existing API contract and UI dependencies

The redesign should continue to use the current server unless a separate backend change is approved.

| Endpoint | Purpose | UI dependency |
|---|---|---|
| `GET /` | Serves `spotui_ui.html` | Loads the application |
| `GET /api/health` | Returns basic health, currently `{ "ok": true }` | Basic server connectivity in Settings |
| `GET /api/now` | Reads current MPRIS track metadata | Now Playing search action |
| `GET /api/search?q=...` | Searches Amazon Music and returns categorized sections | Search results |
| `GET /api/detail?url=...` | Resolves artist, album, or supported playlist detail | Detail workspace |
| `GET /api/queue` | Returns queue job snapshots | Compact queue and full queue manager |
| `POST /api/download` | Enqueues one supported track | Track-row download action |
| `POST /api/download-batch` | Enqueues multiple tracks and returns counts | Album/artist/playlist bulk action |
| `POST /api/cancel` | Cancels a queued job | Cancel action for queued jobs |
| `POST /api/retry` | Requeues a failed job | Retry action for failed jobs |

Current queue fields include job identity, title, artist, URL, status, message, file path, added time, and updated time, with some fields present only for relevant states. The UI must tolerate missing optional fields.

There is no API in the current server for deleting a queue record, retrieving a dedicated archive of completed jobs, or reporting numeric progress. See the queue section for implementation requirements before enabling these features.

## 19. Frontend implementation guidance

The current UI is a single HTML file with embedded CSS and JavaScript, served directly by Python's standard-library HTTP server. The redesign should remain compatible with this deployment unless a separate migration is agreed.

- Keep design tokens in a well-organized `:root` token layer and override them for the dark theme.
- Use a stable CSS class naming system by component, not scattered inline styling.
- Use CSS Grid for the main shell and result grids, Flexbox for rows and controls.
- Keep the app usable if a remote image fails to load or an external font is unavailable.
- Prefer inline SVG icons consistent in stroke weight. Add accessible labels to icon-only controls.
- Keep API calls in a small helper and handle JSON parsing, HTTP errors, and network failures consistently.
- Do not bind new visual controls to unsupported endpoints.
- Avoid frequent full-list re-renders during the queue's current periodic polling. Preserve keyed row reconciliation or equivalent behavior and do not trigger entrance animations on every refresh.
- Keep external network requests limited to the existing product/search behavior and artwork URLs. The UI should not add analytics or third-party tracking.
- If the CSS/JS becomes difficult to maintain, split into local files only after checking how `spotui.py` serves static assets and updating the serving route deliberately. Do not make the page depend on a build step without documenting it.
- Keep the app bound to its intended local interface. This UI specification does not change server network binding or authentication behavior.

## 20. Implementation sequence

Implement in small, reviewable steps. Keep the download backend functional after every step.

### Phase 1: Tokens and shell

- Replace the current amber/earth palette and display/body font pairing with the Material 3 inspired lavender token system and system sans-serif stack.
- Add System, Light, and Dark theme application.
- Establish the navigation rail, global header, central workspace, and right queue panel.
- Add a `backdrop-filter` fallback and restrained frosted treatment.

### Phase 2: Search and detail views

- Rebuild category headers, artist cards, album/playlist cards, and track rows.
- Preserve all result types returned by the API.
- Keep the query and result state when entering and leaving a detail view.
- Build reusable detail headers and track-row components.
- Wire `/` shortcut, Enter submit, and Now Playing search.

### Phase 3: Queue overview and full manager

- Keep the compact queue overview synchronized with `/api/queue`.
- Build the full Queue workspace using actual statuses and messages.
- Wire Cancel and Retry only to their existing supported endpoints.
- Document backend work needed for record removal, persistent history, and numeric progress. Do not add fake controls to the UI.

### Phase 4: Responsive navigation and sheets

- Add the collapsed tablet rail and tablet queue drawer.
- Add phone bottom navigation and the queue bottom sheet.
- Test long queue titles, failure messages, narrow search controls, keyboard behavior, and safe-area padding.

### Phase 5: Settings and feedback

- Add local theme, accent preset if feasible, and reduced-motion preferences.
- Show server connectivity based on `/api/health` only.
- Implement inline errors and short success snackbars.
- Verify that failures remain visible in their relevant workspace.

### Phase 6: Accessibility and regression testing

- Test keyboard-only navigation, focus, screen reader labels, theme contrast, reduced motion, 200 percent zoom, and phone touch targets.
- Test search, detail resolution, individual enqueue, bulk enqueue, duplicate detection, library badges, cancellation, retry, and queue polling.
- Test API-offline, Amazon-search failure, MPRIS unavailable, missing artwork, empty results, and failed downloads.
- Confirm that changing the interface did not modify server-side download resolution or quality behavior.

## 21. Acceptance checklist

### Visual system

- [ ] Lavender/periwinkle accents are restrained and consistent across light and dark themes.
- [ ] System theme is the default and follows the operating system.
- [ ] Major surfaces use the correct neutral surface tokens.
- [ ] Glass appears only on selected chrome and overlays, not every card or row.
- [ ] The interface uses a Roboto-compatible sans-serif and the defined type hierarchy.
- [ ] Cards use approximately 12 px corners and major panels use 14 to 16 px corners.

### Desktop structure

- [ ] The left navigation rail, central workspace, and right compact queue are visible at wide desktop widths.
- [ ] The global search header stays available across all views and is prominent on Search/detail.
- [ ] The queue overview remains visible while the main view changes.
- [ ] The full Queue page occupies the central workspace without removing the right overview.

### Search and detail

- [ ] Results remain categorized by type, including playlist categories returned by the API.
- [ ] Artist artwork is circular; album and playlist artwork is square.
- [ ] Track rows expose the exact result's download action and library status.
- [ ] Clicking an artist/album/playlist opens a dedicated detail view where supported.
- [ ] Back restores the previous search context and scroll position.
- [ ] Now Playing searches the current MPRIS track and handles unavailable metadata cleanly.

### Queue behavior

- [ ] Queue states use text and icon, not color alone.
- [ ] Active/queued/failed states are visible in the compact panel.
- [ ] Retry and cancellation work through supported endpoints.
- [ ] The UI does not claim numeric progress when the backend exposes only phase messages.
- [ ] Removal and persistent history controls remain absent until backend support exists.
- [ ] Queue polling does not cause duplicate DOM rows, repeated animations, or visible flicker.

### Responsive behavior

- [ ] Tablet navigation collapses and the queue opens in a slide-out panel.
- [ ] Phone navigation uses Search, Queue, and Settings in a bottom navigation bar.
- [ ] Phone Queue opens in an accessible frosted bottom sheet.
- [ ] Main content has no unwanted horizontal page scroll on narrow phones.
- [ ] Overlay controls work with touch, mouse, and keyboard.

### Settings, accessibility, and feedback

- [ ] Settings provides System, Light, and Dark themes.
- [ ] Reduced motion honors both system preference and the user's override.
- [ ] Accent presets, if enabled, persist and keep readable contrast.
- [ ] Server status reflects `/api/health` without claiming diagnostics that it does not provide.
- [ ] Actionable failures remain visible inline.
- [ ] Success snackbars are short and do not block interaction.
- [ ] Focus is visible, labels are accessible, and contrast meets WCAG AA targets.
- [ ] No unsupported backend action is presented as functional.

## 22. Final design decisions

These decisions were selected during the design interview and should be treated as the current baseline:

1. **Material treatment:** subtle frosted Material 3. Keep content surfaces solid and readable.
2. **Theme behavior:** System, Light, and Dark with matched palettes and an optional manual override.
3. **Desktop layout:** three zones, left navigation rail, central workspace, persistent right queue overview.
4. **Accent:** lavender and periwinkle.
5. **Search results:** categorized overview with separate Artists, Albums, and Tracks sections, plus other supported categories such as playlists.
6. **Details:** dedicated central detail view with artwork, metadata, track list, and return-to-search behavior.
7. **Queue:** compact live overview on the right and full queue manager in the central workspace.
8. **Search:** persistent global header on Search/detail, keyboard shortcut `/`, explicit submit action, and Now Playing search.
9. **Responsive layout:** desktop rail and queue panel, collapsed tablet rail and slide-out queue, phone bottom navigation and frosted queue sheet.
10. **Density:** balanced spacing and medium album cards, compact but comfortable track rows, responsive columns.
11. **Motion:** gentle Material transitions, small directional changes, smooth drawers/sheets, respect reduced motion.
12. **Typography:** Roboto or compatible system sans-serif with a defined Material 3 scale.
13. **Shape:** softly rounded Material 3, approximately 12 px card corners and 14 to 16 px major panel/dialog corners. Use pills selectively.
14. **Feedback:** layered. Inline persistent errors and queue failure details, short snackbars for success, restrained status icons, no routine modal dialogs.
15. **Settings:** minimal. Theme, reduced motion, accent if feasible, basic app/server information. Keep queue operations in Queue and do not add unsupported controls.

## 23. Source-informed constraints

This specification was written against the supplied SpotUI files, especially `spotui_ui.html` and `spotui.py`.

- The existing UI is a single HTML document with embedded CSS and JavaScript.
- The server currently binds to `127.0.0.1` on port `8765`.
- Search returns categorized result sections, including more than the core Artists, Albums, and Tracks categories in some cases.
- Details are resolved through `/api/detail` and support artists, albums, and supported playlist types.
- Queue processing is a persistent single-worker FIFO. Job status and phase text come from the backend.
- Completed jobs are removed from the visible/persisted queue after roughly three seconds. A lasting history view needs backend support.
- The current queue API has Cancel and Retry operations but no removal endpoint.
- The current health endpoint exposes only a basic `ok` result.

When source behavior and this intended design differ, preserve existing backend behavior until a clearly scoped backend change is implemented and tested. Do not use UI styling to imply functionality that the backend does not provide.
