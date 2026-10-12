# Progress

Status legend: **Done** = works with saved project data and is verified (test or browser check);
**Partial** = works but with a documented gap; **Not started**; **Blocked** (external dependency).

_Last updated: end of session 1 (2026-10-12)._

## Summary

All seven phases are implemented. The full workflow (create style → choose any of the 3 garments → edit
parts → artwork/patterns/textures/stitching/embellishments/hardware → save/reopen → realistic preview →
measurements in cm/in → colorways/materials/BOM/notes → revisioned PDF + CSV + PNG exports) works end to end
and is covered by automated tests.

The one material gap is **ghost-mockup asset quality**: the renderer is complete, but its shading assets are
procedurally authored vector folds (`procedural-v1`), not extracted from photographs of physical samples.
Those photos don't exist in this environment, so I can't produce photographic assets here. The previews are
convincing appearance previews and are labelled as procedural in the UI and documents. The photographic
asset specification is in `TEMPLATE_AUTHORING.md` §4.

## Checks performed

| Check | Result |
|---|---|
| `npm run typecheck` | clean |
| `npm test` (Vitest: units, sanitizer, domain, templates, API + PDF integration) | 51 / 51 passing |
| `npm run test:e2e` (Playwright, real browser, 5 workflows) | 5 / 5 passing |
| `npm run build` + `npm start` (production serve) | serves app + API |
| PDF inspection | Rasterised every page of the T-shirt, hoodie and sweatpants packs and inspected them visually. An automated text-bounds test checks every page for in-page text, style number, revision and page numbering. |
| UI inspection | Screenshots of all six screens at 1440×900 and at 390 px width (no horizontal overflow) |

## Requirement status

| ID | Status | Notes / evidence |
|---|---|---|
| WRK-01 | Done | The repo-root profile `README.md` is left untouched; the app lives in `apparel-studio/`. |
| WRK-02 | Done | All four documents are maintained. |
| WRK-03 | Done | Built in phases, each with tests and screenshots. |
| WRK-04 | Done | Every control writes to the validated project document (autosaved). |
| WRK-05 | Done | The ghost-asset gap is documented (see GHO-01/05). |
| WRK-06 | Done | Continuation note is at the end of this file. |
| OUT-01 | Done | e2e `T-shirt: design → specs → revisioned tech pack`. |
| OUT-02 | Done | The BOM, flats, callouts and specs are all computed from the document (`shared/domain`, `shared/render`). |
| OUT-03 | Done | `domain.test` "linked material changes update the BOM reference"; e2e Materials step. |
| OUT-04 | Done | `applyEnteredPlacement` updates both the spec and the canvas; domain test + e2e. |
| OUT-05 | Done | Counted rows come from placements; domain test + e2e (3 placed → qty 3). |
| OUT-06 | Done | Snapshot + DB immutability trigger; API test "issued revisions are immutable". |
| TEC-01 | Done | React + Vite, Express, SQLite, content-addressed storage. |
| TEC-02 | Done | `npm install && npm run dev`; no external services. |
| TEC-03 | Done | `StorageAdapter` interface (`src/server/storage.ts`). |
| TEC-04 | Done | Vector templates (`shared/templates`), one `TechView` renderer. |
| TEC-05 | Done | `client/render/ghost.ts`: deterministic (seeded noise, no randomness). |
| TEC-06 | Done | Zod schemas, validated client-side before save and server-side on PUT, plus integrity checks. |
| TEC-07 | Done | pdfkit + svg-to-pdfkit; embedded DejaVu fonts; failures are recorded per export and can be retried. |
| TEC-08 | Done | Nothing in V1 does 3D, pattern drafting, fit simulation, AI geometry or grading. |
| TEC-09 | Done | No AI services are used anywhere. |
| GAR-01 | Done | Boxy T-shirt v1. |
| GAR-02 | Done | Pullover hoodie v1: lined two-panel hood, kangaroo pocket, rib cuffs and hem band, drawcord. |
| GAR-03 | Done | Straight-leg sweatpants v1: elastic waistband, drawcord, side-pocket openings, back patch pocket. |
| GAR-04 | Done | Front and back views for all three garments; drawn at nominal 1 mm/unit and checked visually. |
| GAR-05..09 | Done | Panels, components, seams, anchors, POMs and diagrams. A template test checks anchor containment and that drawn POM lines match default values. |
| GAR-10 | Done | `decorationMethods` per component; validated on export. |
| GAR-11 | Partial | Matched assets exist for all garments and views, but at `procedural-v1` quality (not photographic). |
| GAR-12 | Done | Flats are drafted from real proportions with seams, ribs and trims; no generic blobs. They are not derived from production patterns. |
| GAR-13 | Done | The demo "Sunset Club Lounge Set" collection groups hoodie + sweatpants; each has its own spec and tech pack. |
| GAR-14 | Done | `structure` is immutable; the decorative zipper is visual-only with an explicit note in the UI and tech pack. |
| SCH-01 | Done | Templates are versioned and frozen, and a lock-file test fails if a published version changes. |
| SCH-02..07 | Done | See `schema/template.ts` and `schema/project.ts`. The API test checks the save/reload round trip (incl. masks and assets). |
| EDT-01..06 | Done | Design Studio. Zoom = wheel/buttons; pan = Space-drag, middle-drag or the hand tool; Delete key; Ctrl/⌘+D duplicates. |
| EDT-07 | Done | Reorder/lock/hide in Layers. Rename in the inspector or by double-clicking (this uses a browser prompt). |
| EDT-08..09 | Done | Approachable labels. Parts view by default; Layers tab for finer control. |
| EDT-10..11 | Done | e2e recolor test. "Make different on back only" / "Re-link to all views". |
| ART-01..13 | Done | PNG signature + alpha check; SVG sanitizer tests; clip-to-panels with an explicit purple outline; multi-panel targets. |
| PAT-01..02 | Done | Uploaded tiles with physical repeat width, rotation, offsets, opacity and panel targets. |
| PAT-03..06 | Done | 10 curated procedural textures. Each can be set per panel or come from the material, and links to a material. |
| PAT-07..10 | Done | Per-view vector mask strokes; erase/restore/reset. e2e "Erasing one pattern leaves every other layer untouched". |
| DEC-01..04 | Done | Stitching on template seams, with color, style and notes. Shown as illustrative in the UI and PDF. |
| DEC-05..11 | Done | Point and path placement with editable points and per-path spacing; diameter/finish/attachment; counted. Gap: you can't insert a point into the middle of an existing path (delete and redraw instead). |
| DEC-12..15 | Done | 8 catalog items. Counted BOM rows link back to the layers. Structural notes are displayed. |
| MEA-01..10 | Done | Canonical mm grid; fraction parsing; unit tests show no drift; unconfirmed defaults flagged; review export requires entered dimensions; no grading. |
| GHO-01 | Partial | Every asset role is implemented. Occlusion uses the z-ordered panel id-map rather than a separate mask asset. Assets are procedural. |
| GHO-02..04 | Done | Pipeline order is documented in `TEMPLATE_AUTHORING.md`. Treatments: print/DTG (ink sits on the knit), embroidery/appliqué/puff (raised), rhinestone glints, stud highlights. Screen print and DTG share one treatment. |
| GHO-05 | Partial | The T-shirt render has believable volume and folds, but it isn't photoreal (procedural assets). |
| GHO-06 | Done | Photographic asset spec is in `TEMPLATE_AUTHORING.md` §4. The UI labels previews "procedural shading assets". |
| GHO-07 | Done | Technical view and PDF flats are independent of the ghost renderer. |
| CMB-01..07 | Done | Palette with user-supplied standards and approval status; materials; BOM with counted/entered/estimated; colorway substitutions. |
| TPK-01..21 | Done | API tests cover sections, header/footer on every page, text bounds, gating, immutability and CSV injection guard. e2e covers PDF/CSV/PNG downloads. |
| SCR-01..06 | Done | All six screens work with saved data. |
| SCR-07 | Done | Labels, roles, focus styles and empty/error states are in place. No formal WCAG audit has been run. |
| SCR-08 | Done | Responsive layout checked at 390 px. Editing on a phone works but is cramped. |
| VER-01..15 | Done | VER-01/02/03/04/06/07/10 in e2e + unit; VER-05 e2e; VER-08 e2e + unit; VER-09 unit + e2e; VER-11..14 API tests. |
| CMP-01..06 | Done | e2e. |
| CMP-07 | Partial | Realistic previews are available for all three garments, using procedural assets. |
| CMP-08..11 | Done | — |

## Known limitations

1. **Ghost assets are procedural.** Folds are hand-authored and generic per garment; they don't respond to
   the measurement values (V1 doesn't simulate fit, by design).
2. **Single-user, local.** There's no authentication. Concurrent edits in two tabs are detected (HTTP 409 →
   "Reload"), not merged.
3. **Blob storage is never garbage-collected.** Files stay forever, which keeps issued revisions safe.
4. **Path editing:** you can move or delete path points and whole paths, but not insert a point mid-path.
5. **Text inside uploaded SVGs** prints in DejaVu Sans in the PDF (no font embedding from uploads).
   Convert text to outlines for exact typography.
6. **No machine files** (DST, colour separations) are produced. This is intentional; previews are appearance-only.
7. Template geometry is a nominal drawing at size M. It isn't derived from production patterns.

## Continuation note

- **Current phase:** V1 feature-complete. Remaining work is quality and polish, not missing features.
- **Key files:** `src/shared/**` (schemas, templates, domain, TechView), `src/server/**` (API, PDF/CSV,
  revisions, sanitizer, demo seed), `src/client/**` (screens, editor, ghost renderer), `scripts/ghost/specs.ts`,
  `tests/**`, `e2e/**`.
- **How to verify:** `npm run typecheck && npm test && npm run test:e2e`.
- **Next steps (suggested order):**
  1. Commission ghost-mannequin photos of physical samples and build `photographic` asset sets (spec in
     `TEMPLATE_AUTHORING.md` §4). Publish them as template v2 so v1 projects stay unchanged.
  2. Allow inserting points into embellishment paths, and add snapping to seams.
  3. Run an accessibility audit (keyboard-only canvas editing, screen-reader labels for canvas items).
  4. Add an S3/GCS `StorageAdapter`, plus Postgres if multi-user is needed (the schema is portable).
  5. Add more garments with the same template system (see the checklist in `TEMPLATE_AUTHORING.md` §5).
