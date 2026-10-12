# Apparel Studio

Design clothing and generate a professional tech pack from the **same saved design** — no Illustrator,
no re-typing your design into a separate tech-pack tool.

**Workflow:** create a style → choose a garment → customize individual parts → add artwork,
patterns, textures, stitching, rhinestones/studs and hardware → preview a realistic ghost mockup →
enter measurements and manufacturing details → export a revisioned tech pack (PDF + CSVs + mockup PNGs).

Garments in V1: **Boxy T-shirt**, **Pullover hoodie**, **Straight-leg sweatpants**.

## Quick start (local, no paid services)

Requirements: Node.js 20+ (22 recommended) and npm. Windows, macOS, or Linux.

```bash
cd apparel-studio
npm install
npm run dev
```

Open http://localhost:5173. On first start the API seeds a **demonstration project set** (see below).
Data lives in `apparel-studio/data/` (SQLite database + uploaded/exported files). Delete that
folder to start fresh (the demo is re-seeded; set `NO_DEMO=1` to skip it).

| Command | What it does |
|---|---|
| `npm run dev` | API (http://localhost:4000) + web app with hot reload (http://localhost:5173) |
| `npm run build && npm start` | Production build served by the API on http://localhost:4000 |
| `npm test` | Unit + API integration tests (Vitest) |
| `npm run test:e2e` | End-to-end browser tests (Playwright; starts its own servers on ports 4100/5174 with a throwaway data folder). First time: `npx playwright install chromium` unless a Chromium is preinstalled (`CHROME_PATH` env var is honoured). |
| `npm run typecheck` | TypeScript check |
| `npm run seed` | Add another copy of the demo projects |
| `npm run sample:techpack -- out.pdf` | Render the demo tech pack to a file without running the server |
| `npm run build:ghost` | Regenerate ghost-mockup shading assets from `scripts/ghost/specs.ts` |

Environment variables: `PORT` (API, default 4000), `DATA_DIR` (default `./data`), `NO_DEMO=1`.

## Demonstration project

The seeded projects exercise the complete workflow:

- **Sunset Club Boxy Tee (demo)** — navy sleeves & rib on a white body (per-part colors), a screen-printed
  chest logo with entered manufacturing dimensions and tolerance, a back badge whose size is still a
  *visual estimate*, a sun-dot all-over pattern on both sleeves with a non-destructive erased band, contrast
  hem coverstitch with manufacturing notes, a neckline rhinestone trail (counted in the BOM), a second
  colorway (“Sand / navy”), measurements for XS–XL with one POM left unconfirmed, construction notes,
  labels/packaging and a manual BOM row. It intentionally has **2 open required items**, so you can see the
  draft vs. ready-for-review gate: confirm POM **L** on *Measurements* and enter the back badge size on the
  *Design Studio* to unlock the review export.
- **Sunset Club Lounge Set** collection — **Hoodie (demo)** with embroidered chest logo, puff-printed hood,
  contrast topstitch and a metal badge; **Sweatpants (demo)** with an embroidered thigh logo and a stud stripe.
  Each keeps its own specification and tech pack. Their measurements are still template defaults
  (unconfirmed) — a realistic starting point.

## What’s where

```
apparel-studio/
  src/shared/      Single source of truth used by browser AND server
    schema/        Zod schemas: garment templates, project document (discriminated layer union)
    templates/     Versioned, immutable garment templates (+ ghost asset manifests, lock file)
    domain/        Placement ↔ canvas mapping, BOM derivation, embellishment counting, validation
    render/        TechView: the vector technical drawing (editor, PDF and mockup passes all use it)
    catalog/       Curated textures, hardware, rhinestone/stud sizes
    units.ts       Decimal-safe mm canonical units, cm/in parsing (fractions) and formatting
  src/server/      Express API, SQLite (better-sqlite3), storage adapter, SVG sanitizer, PDF/CSV exports
  src/client/      React app: Projects, Choose garment, Design Studio, Measurements, Materials & Colors, Tech Pack
    render/ghost.ts  Deterministic 2D ghost-mockup renderer (Canvas)
  public/ghost/    Generated shading / highlight / displacement maps per garment & view
  scripts/         Asset generator, template lock, sample tech pack, dev helpers
  tests/ e2e/      Vitest and Playwright suites
```

**Stack.** TypeScript everywhere; React 18 + Vite; Zustand + Immer (document store with undo/redo and
debounced autosave with optimistic concurrency); Express + SQLite (relational tables for projects,
assets, revisions, exports; the validated project document is stored as JSON); content-addressed local
file storage behind a `StorageAdapter` interface (swap in S3/GCS without touching callers); pdfkit +
svg-to-pdfkit for vector PDFs with embedded DejaVu fonts.

## Important behaviours

- **One source of truth.** The tech pack, BOM and CSVs are computed from the saved design. Changing a
  sleeve’s material changes its BOM row; entering a logo’s finished width resizes it on the canvas and
  updates its placement spec; placing rhinestones updates their counted quantity.
- **Physical units.** Stored in millimetres (4-decimal grid). The cm/in toggle only changes display;
  inches accept decimals or fractions (`12 3/8`).
- **Placement honesty.** Templates are drawn at a *nominal* scale (1 unit = 1 mm at size M). Dragging on the
  canvas produces a *visual estimate*; a manufacturer-review export requires entered finished dimensions.
- **Measurements.** Template values are flagged as unconfirmed defaults; no grading rules are applied. V1 does
  not simulate fit or drape — changing measurements does not refit the mockup.
- **Revisions are immutable.** Each export freezes a snapshot (document, template, BOM, checks, asset hashes);
  a database trigger rejects updates to issued revisions. Draft exports list open items; “Ready for manufacturer
  review” requires all required checks. Nothing is ever labelled manufacturer-approved.
- **Uploaded SVG is untrusted.** Scripts, event handlers, `foreignObject`, external links/`url()`s, CSS `@import`
  and DTD/entities are removed or rejected; files are served with a restrictive Content-Security-Policy.
- **Ghost mockups** are appearance previews from a deterministic renderer using *procedurally authored*
  shading assets (not photographs). See `TEMPLATE_AUTHORING.md` and `PROGRESS.md` for the honest status.

See `PRODUCT_REQUIREMENTS.md` (requirement IDs), `IMPLEMENTATION_PLAN.md`, `PROGRESS.md` (status per
requirement + continuation notes) and `TEMPLATE_AUTHORING.md`.
