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
| UI-035 | On failure the UI MUST show `x could not reach Brain API` (all errors, including 4xx/5xx, show this same message). Error text SHOULD distinguish causes. | ⚠️ |
| UI-036 | A tag typed but not confirmed with Enter/`,` is not included on submit. | ⚠️ |

## 5. Recent Entries

| ID | Requirement | Status |
|----|-------------|--------|
| UI-040 | On load and after each ingest, the UI MUST fetch `GET /entries?limit=30` and render cards. | ✅ |
| UI-041 | Each card shows content (clamped to 2 lines), date (e.g. "Oct 19"), `via <source>`, type badge (hidden if `other`), tags, and topics. | ✅ |
| UI-042 | Clicking a card fills the search box with the first 60 characters of the entry and clears results (it does not auto-run search). | ✅ |
| UI-043 | A delete (✕) button appears on card hover. Clicking removes the entry via `DELETE /entries/{id}` and removes it from local state. | ✅ |
| UI-044 | Delete has no confirmation prompt and no error feedback on failure (UI removes the card even if the request returned an error status). A confirmation SHOULD be added. | ⚠️ |
| UI-045 | Deleting an entry does not clear it from any currently displayed search results. | ⚠️ |
| UI-046 | Empty list shows "nothing stored yet". | ✅ |

## 6. Search

| ID | Requirement | Status |
|----|-------------|--------|
| UI-050 | A search input and button; Enter submits. Blank queries are ignored. | ✅ |
| UI-051 | Search calls `POST /search` with `limit: 8`. | ✅ |
| UI-052 | During search the UI shows "querying brain..." with an animated ellipsis. | ✅ |
| UI-053 | Initial state shows a "semantic search" explanatory empty state; zero results shows "no results — try rephrasing, or store more thoughts first". | ✅ |
| UI-054 | Each result card shows match percentage (`score × 100`) with a bar, type badge (hidden if `other`), full content (whitespace preserved), date, source, tags, topics, people, and an "action items" list when present. | ✅ |
| UI-055 | Search errors are swallowed and displayed as "no results"; the user cannot tell failure from empty. | ⚠️ |
| UI-056 | The UI has no filters (source/type/tag/date) and no way to view `/stats`. | ❌ |
