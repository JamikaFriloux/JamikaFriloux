# Implementation Plan

## Stack (decided)
- **Client:** React 18 + TypeScript, Vite, React Router, Zustand + Immer (document store with undo/redo).
- **Server:** Express (TypeScript via `tsx`), SQLite via `better-sqlite3` (relational tables for projects,
  assets, revisions, exports; the validated project document is stored as JSON in the project row).
- **Assets:** `StorageAdapter` interface with a local-filesystem implementation (content-addressed by
  SHA-256). An S3-style adapter can be dropped in without touching callers.
- **Shared core (`src/shared`):** Zod schemas, versioned garment templates, unit math, BOM derivation,
  embellishment counting, export validation, SVG technical-view renderer (React component that renders
  in the browser *and* through `react-dom/server` for PDFs — one drawing source).
- **PDF:** `pdfkit` + `svg-to-pdfkit` (vector flats), DejaVu Sans embedded for Unicode text.
- **Ghost mockups:** deterministic Canvas 2D pipeline in the browser (`src/client/render/ghost`), using
  per-template asset manifests (mesh mapping, shadow/highlight/displacement maps, occlusion).
- **Tests:** Vitest (unit + API integration with supertest), Playwright (end-to-end workflow).

Why: everything runs locally with `npm install && npm run dev`, no paid services, no native services
beyond SQLite. Each piece (storage, DB, renderer, PDF) sits behind a module boundary.

## Phases

Status (end of session 1): phases 1–7 implemented and verified. GHO assets are at `procedural-v1`
quality (see PROGRESS.md for the per-requirement status).

### Phase 1 — Foundation — ✅ done
Reqs: TEC-01..07, SCH-01..07, GAR-01 (geometry), GAR-04..09 (tee), MEA-02, ART-12, CMP-11 (setup).
Deps: none.
Acceptance:
- Zod schemas for template + project with discriminated layer union; invalid docs rejected by API.
- Boxy T-shirt template v1 (front/back panels, components, seams, anchors, POMs).
- Sample/demo project seeded.
- Asset upload (PNG validated by signature, SVG sanitized) stored content-addressed.
- Save/load round trip (API test) with optimistic concurrency.

### Phase 2 — Vector editing — ✅ done
Reqs: EDT-01..11, ART-01..06, ART-11, ART-13, VER-01..04, VER-06.
Deps: Phase 1.
Acceptance: editor with front/back, panel recolor scoped to one component, logo upload + transforms,
clipping to selected panels, layers panel (order/lock/visibility/name), undo/redo that persists,
saving status; e2e test covers recolor + upload + reload.

### Phase 3 — Manufacturing specifications — ✅ done
Reqs: MEA-01..10, ART-07..10, CMB-01..06, OUT-03, OUT-04, VER-07..09.
Deps: Phase 2.
Acceptance: Measurements screen with POM diagram + size table (cm/in), confirmation states;
placement spec linked to canvas; palette/materials/BOM screen with derived rows; validation engine.

### Phase 4 — First complete tech pack — ✅ done
Reqs: TPK-01..15, TPK-17..21, OUT-06, VER-11..14.
Deps: Phase 3.
Acceptance: revision snapshot endpoint; PDF with all sections and header/footer; CSV exports; draft vs
review gating; immutability test; PDF text-bounds test.

### Phase 5 — Ghost rendering — ✅ renderer done, assets partial (procedural, not photographic)
Reqs: GHO-01..07, TPK-16, CMP-07.
Deps: Phase 2 (renderer consumes the same layers).
Acceptance: T-shirt renders with panel colors, textures, artwork mapped through mesh + displacement,
shading multiply/screen, occlusion; PNG export; honest labeling of asset quality.

### Phase 6 — Advanced decoration — ✅ done
Reqs: PAT-01..10, DEC-01..15, OUT-05, VER-05, VER-10.
Deps: Phases 2–5.
Acceptance: patterns with tiles + transforms, persistent erase/restore masks with reset, stitching on
seams, rhinestones/studs (points + path), hardware catalog with BOM links, counts in BOM.

### Phase 7 — Complete V1 — ✅ done
Reqs: GAR-02, GAR-03, GAR-13, GAR-14, CMB-07, SCR-01..08, CMP-01..11.
Deps: all.
Acceptance: hoodie + sweatpants templates and ghost assets, colorways, collections, all screens,
demo project, setup docs, full test suite green, honest PROGRESS.md.
