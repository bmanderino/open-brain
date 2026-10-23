# 04 — Web UI

**Implementation:** `web-ui/src/App.jsx` (single component, inline CSS), built with Vite, served by nginx on host port 5173. Dark theme. Fonts referenced: Syne (display), Martian Mono (body); they are referenced by name in CSS (verify `index.html` loads them).

## 1. Runtime Configuration

| ID | Requirement | Status |
|----|-------------|--------|
| UI-001 | The API base URL MUST be configurable at container start via `BRAIN_API_URL`; `entrypoint.sh` writes `/usr/share/nginx/html/config.js` setting `window.__BRAIN_CONFIG__.apiUrl`. | ✅ |
| UI-002 | The default API URL is `http://localhost:8000` (browser-side; must be reachable from the user's browser, not the container). | ✅ |
| UI-003 | nginx MUST serve the SPA with fallback to `index.html`. | ✅ |

## 2. Layout

| ID | Requirement | Status |
|----|-------------|--------|
| UI-010 | Header with logo "openbrain / knowledge layer" and a connection indicator (green pulsing "connected" / red "offline"). | ✅ |
| UI-011 | Two-column body: left panel (380 px) = capture + recent list; right panel = search bar + results. | ✅ |
| UI-012 | The layout is desktop-oriented (fixed 380 px column, no responsive breakpoints). | ⚠️ |

## 3. Connection Status

| ID | Requirement | Status |
|----|-------------|--------|
| UI-020 | On load, the UI MUST call `GET /health` once and show connected/offline. | ✅ |
| UI-021 | Status is not re-polled; it can go stale until reload. It SHOULD poll or update on request failures. | ⚠️ |

## 4. Capture

| ID | Requirement | Status |
|----|-------------|--------|
| UI-030 | A multi-line textarea MUST accept content; Ctrl/Cmd+Enter submits. | ✅ |
| UI-031 | Tags: typing text and pressing Enter or `,` adds a tag chip; duplicates are ignored; clicking a chip removes it. | ✅ |
| UI-032 | The "store in brain" button MUST be disabled when content is blank or while submitting, and show "storing...". | ✅ |
| UI-033 | Submit calls `POST /ingest` with `source: "web-ui"`. | ✅ |
| UI-034 | On success the UI MUST show `-> stored in brain [type] — topics`, clear the textarea and tags, and refresh the recent list. | ✅ |
| UI-035 | On failure the UI MUST show `x <reason>`: `could not reach Brain API` when the request itself fails (network), otherwise the API's error `detail` (or `HTTP <status>` if it has none), e.g. `x Ollama embedding failed: ...`. | ✅ |
| UI-037 | If the API reports `duplicate_of`, the UI MUST show `= not stored: a near-duplicate entry already exists` (as an error-style message) instead of the success text, and clear the form. | ✅ |
| UI-038 | If `metadata_status` is `failed`, the success text MUST end with `(metadata extraction failed)`. | ✅ |
| UI-036 | A tag typed but not confirmed with Enter/`,` is not included on submit. | ⚠️ |

## 5. Recent Entries

| ID | Requirement | Status |
|----|-------------|--------|
| UI-040 | On load and after each ingest, the UI MUST fetch `GET /entries?limit=30` and render cards. | ✅ |
| UI-041 | Each card shows content (clamped to 2 lines), date (e.g. "Oct 19"), `via <source>`, type badge (hidden if `other`), tags, and topics. | ✅ |
| UI-042 | Clicking a card fills the search box with the first 60 characters of the entry and clears results (it does not auto-run search). | ✅ |
| UI-043 | A delete (✕) button appears on card hover. Clicking asks for confirmation (`window.confirm`, showing the first 80 characters), then removes the entry via `DELETE /entries/{id}` and from local state. Cancelling does nothing. | ✅ |
| UI-044 | If the delete fails (network or an HTTP error other than 404) the card MUST stay and the UI shows `x could not delete: <reason>` in the capture panel's message area. A 404 (already gone) removes the card. | ✅ |
| UI-045 | Deleting an entry does not clear it from any currently displayed search results. | ⚠️ |
| UI-046 | Empty list shows "nothing stored yet". | ✅ |
| UI-047 | If loading the list fails, the list shows `x could not load entries: <reason>` instead of "nothing stored yet". | ✅ |

## 6. Search

| ID | Requirement | Status |
|----|-------------|--------|
| UI-050 | A search input and button; Enter submits. Blank queries are ignored. | ✅ |
| UI-051 | Search calls `POST /search` with `limit: 8`. | ✅ |
| UI-052 | During search the UI shows "querying brain..." with an animated ellipsis. | ✅ |
| UI-053 | Initial state shows a "semantic search" explanatory empty state; zero results shows "no results — try rephrasing, or store more thoughts first". | ✅ |
| UI-054 | Each result card shows match percentage (`score × 100`) with a bar, type badge (hidden if `other`), full content (whitespace preserved), date, source, tags, topics, people, and an "action items" list when present. | ✅ |
| UI-055 | A failed search (network or HTTP error) MUST show a "search failed" state with the reason, not "no results"; the error clears on the next search. | ✅ |
| UI-056 | The UI has no filters (source/type/tag/date) and no way to view `/stats`. | ❌ |

## 7. Pinning, Related Entries, Supersession

Entry cards and search results share the actions below. Card actions appear on hover; on search results they are always visible. These were not run against a browser in CI (the UI has no tests, only a production build).

| ID | Requirement | Status |
|----|-------------|--------|
| UI-060 | Pinned entries show a `pinned` badge. A `pin` / `unpin` action calls `PATCH /entries/{id}` with `pinned` and updates the entry everywhere it is displayed. A failure shows `x could not update: <reason>`. | ✅ |
| UI-061 | Superseded entries show a `superseded` badge and are dimmed. By default they are not requested; a "show superseded" checkbox above the recent list sends `include_superseded` to `/entries`, `/search` and `/related`. Search results already on screen are not refreshed when the box is toggled. | ✅ |
| UI-062 | A `related` action opens a panel at the top of the results area, from `GET /entries/{id}/related`, listing each neighbor with date, similarity percentage and badges. Clicking a neighbor opens its own related list. The panel shows a loading line, `nothing similar enough` when empty, and the error on failure, and has a close button. | ✅ |
| UI-063 | After storing an entry whose ingest response has `possibly_supersedes`, the success message ends with `-- N similar, see right panel` and the panel opens titled `possibly replaces`. Each neighbor in the panel has an `outdated` action that supersedes it by the entry named in the panel header. A superseded entry offers `restore`, which clears `superseded_by`. An entry that becomes superseded leaves the lists unless superseded entries are shown. | ✅ |
| UI-064 | The UI cannot choose an arbitrary replacement for an entry; `outdated` only works from a related or possibly-replaces panel. | ⚠️ |

