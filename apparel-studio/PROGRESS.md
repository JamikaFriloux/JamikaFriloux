# Progress & verification audit

_Audit date: 2026-10-12 (session 2). Every ID from `PRODUCT_REQUIREMENTS.md` is listed._

## How to read this

Three kinds of evidence are kept separate:

| Column | Meaning |
|---|---|
| **Impl.** | Code exists and is reachable from the UI or API. |
| **Tested** | An automated test asserts the behaviour on saved data. The test is named in the Evidence column. |
| **Visual** | I looked at the real UI screenshot or exported file. The file is under `verification/`. |

**Status:**
- **Verified** — implemented, tested, and visually checked wherever a visual result applies.
- **Partial** — works, with a specific limitation stated in the row.
- **Missing** — not implemented.
- **Blocked** — needs something this environment cannot provide.

An interface or renderer that merely exists is never counted as Verified.

Abbreviations used in the Evidence column:
- `demo:` = `e2e/demo.spec.ts`. Its results are in `verification/results.json` (54 / 54 checks passed).
- `e2e:` = the other Playwright specs.
- `unit:` / `api:` / `tpl:` = Vitest files in `tests/`.
- `shots:` = screenshots in `verification/<garment>/`.
- `pdf:` = exported PDFs in `verification/<garment>/`.

## Summary

- **Verified:** 164 of 170 requirement IDs.
- **Partial (5):** GAR-11, GHO-01, GHO-03, GHO-05, CMP-07. All five are the same underlying gap:
  the ghost-mockup assets are procedurally drawn, not photographic. The renderer works; convincing
  photographic integration has not been demonstrated. Plan: `ASSET_ACQUISITION_BRIEF.md`.
- **Partial, other (1):** SCR-07 accessibility. The automated scan is clean, but there's no manual
  screen-reader audit, and drawing paths or placing stones still needs a pointer.
- **Missing:** none of the original requirements. Seam snapping is a separate enhancement, not built.
- **Blocked:** photographic assets (an external dependency, see the brief).

## Checks run this session

| Check | Result |
|---|---|
| `npm run typecheck` | clean |
| `npm test` (Vitest) | 52 / 52 passing |
| `npm run test:e2e` | 12 / 12 passing: `workflow` ×5, `editing` ×3, `accessibility` ×1, `demo` ×3 |
| Demonstration runs (T-shirt full, hoodie, sweatpants) | 54 / 54 recorded checks passed (`verification/results.json`) |
| Automated PDF text check (`scripts/pdf-bounds.mts`) | 33 pages, 0 text outside the page, 0 overlapping text |
| Manual PDF inspection | All 33 pages of the 3 verification PDFs viewed at 75 dpi; affected pages re-viewed after fixes |
| axe-core WCAG 2.1 A/AA scan, 14 screen states | 0 serious/critical violations (moderate/minor not gated) |
| Small-screen check, 390 px (`scripts/small-screen-check.mjs`) | 0 page and 0 inner-scroll overflow on 5 screens; `verification/small-screen/` |
| Ghost renderer determinism | Two 3× renders byte-identical (`e2e: editing › deterministic`) |

### Defects found by this verification and fixed

1. **PDF:** bold table cells were measured with the regular font, so wrapped names (e.g. "Flat cotton
   drawcord 12 mm") overlapped the next row. The automated overlap check was strengthened so it
   catches this, and it is now enforced in `api.test`.
2. **PDF:** trims printed "MISSING" in red for weight, although weight isn't required for trims. The
   BOM category for trims was "fabric". The Category column wrapped "embellishment" mid-word.
3. **PDF:** detail views of long seams were framed as a thin sliver. They are now real close-ups.
4. **Editor:** "Add stitching" with no part selected defaulted to an arbitrary join seam on the hoodie
   (a shoulder). It now defaults to the garment's visible topstitch seams. A stitching layer's
   auto-generated name now follows its seams.
5. **Measurements:** re-typing a value equal to the template default didn't record it as
   user-entered. The "Template default" source label also stayed after every value had been entered.
6. **Uploads:** every SVG triggered a false "removed 1 unsafe element" warning (DOMPurify's internal
   wrapper was being counted).
7. **Small screens:** the size table forced the measurement diagram to about 940 px wide, and tab
   labels were clipped. My earlier overflow check had missed this because it ignored the inner scroll
   container; the check was fixed.
8. **Accessibility:** invalid ARIA attributes on tabs, toggles and list rows; 18 dropdowns without
   accessible names; low-contrast hint and badge text.

## Requirement status

| ID | Status | Impl. | Tested | Visual | Evidence / limitation |
|---|---|---|---|---|---|
| WRK-01 | Verified | ✓ | – | ✓ | The profile README at the repo root is untouched; the app is in `apparel-studio/`. |
| WRK-02 | Verified | ✓ | – | ✓ | Four documents, plus `ASSET_ACQUISITION_BRIEF.md` and `verification/README.md`. |
| WRK-03 | Verified | ✓ | ✓ | ✓ | This audit: tests, screenshots, PDF page review. |
| WRK-04 | Verified | ✓ | ✓ | ✓ | demo: every step asserts the saved document through the API. |
| WRK-05 | Verified | ✓ | – | ✓ | The photographic-asset gap is documented and marked Partial. |
| WRK-06 | Verified | ✓ | – | – | Continuation note at the end of this file. |
| OUT-01 | Verified | ✓ | ✓ | ✓ | demo T-shirt: create → … → export R1. shots `tshirt/01…18`. |
| OUT-02 | Verified | ✓ | ✓ | ✓ | BOM, flats and specs are derived from the document. pdf pages 2–5 match shots `12-bom`, `05-logo-placement-spec`. |
| OUT-03 | Verified | ✓ | ✓ | ✓ | demo "Material change updates BOM reference" (Cotton mesh → left sleeve). pdf p.4. |
| OUT-04 | Verified | ✓ | ✓ | ✓ | demo "Logo manufacturing placement entered" + "Canvas follows entered dimensions". pdf p.5. |
| OUT-05 | Verified | ✓ | ✓ | ✓ | demo "Rhinestone BOM count = placements" (26 = canvas badge). pdf p.4/5, BOM CSV. |
| OUT-06 | Verified | ✓ | ✓ | – | demo "Issued revision unchanged after later edit" (snapshot hash and PDF SHA-256 equal). api immutability test; DB trigger. |
| TEC-01 | Verified | ✓ | ✓ | – | React/Vite, Express, SQLite, content-addressed storage. |
| TEC-02 | Verified | ✓ | ✓ | – | All tests run locally; no external services. |
| TEC-03 | Verified | ✓ | – | – | `StorageAdapter` interface (`src/server/storage.ts`); only the local adapter exists. |
| TEC-04 | Verified | ✓ | ✓ | ✓ | tpl suite; flats in pdf p.2. |
| TEC-05 | Verified | ✓ | ✓ | ✓ | e2e deterministic render test. Determinism is verified within one browser build, not across GPUs or browsers. |
| TEC-06 | Verified | ✓ | ✓ | – | api: invalid and broken-reference documents rejected (422). |
| TEC-07 | Verified | ✓ | ✓ | ✓ | api PDF tests; 33 pages reviewed. |
| TEC-08 | Verified | ✓ | – | – | By code inspection: no 3D, pattern drafting, fit simulation, AI geometry or grading. |
| TEC-09 | Verified | ✓ | – | – | By code inspection: no AI services. |
| GAR-01 | Verified | ✓ | ✓ | ✓ | tpl; shots `tshirt/*`. |
| GAR-02 | Verified | ✓ | ✓ | ✓ | tpl; demo hoodie; shots `hoodie/*`. |
| GAR-03 | Verified | ✓ | ✓ | ✓ | tpl; demo sweatpants; shots `sweatpants/*`. |
| GAR-04 | Verified | ✓ | ✓ | ✓ | pdf p.1–2 for each garment. Limitation: the flats are drafted at nominal size M and have not been reviewed by a technical designer. |
| GAR-05 | Verified | ✓ | ✓ | ✓ | demo recolors exactly one part per garment. |
| GAR-06 | Verified | ✓ | ✓ | ✓ | Parts list (shots), colorway table pdf p.3. |
| GAR-07 | Verified | ✓ | ✓ | ✓ | tpl; stitching on seams, pdf p.9. |
| GAR-08 | Verified | ✓ | ✓ | ✓ | tpl checks anchors sit inside their components; placement text pdf p.5. |
| GAR-09 | Verified | ✓ | ✓ | ✓ | tpl checks diagram line lengths match the defaults; pdf p.6–8. |
| GAR-10 | Verified | ✓ | ✓ | – | unit validation rejects unsupported methods. |
| GAR-11 | **Partial** | ✓ | ✓ | ✓ | Matched assets exist for every garment and view, but they are procedural, not photographic. |
| GAR-12 | Verified | ✓ | – | ✓ | Visually coherent flats with seams, ribs and trims. Not pattern-derived. |
| GAR-13 | Verified | ✓ | ✓ | ✓ | e2e projects test shows the "Sunset Club Lounge Set" group; each garment has its own tech pack. |
| GAR-14 | Verified | ✓ | ✓ | ✓ | tpl structure test. The hardware inspector shows "construction remains: pullover" (shot `hoodie/02`). Every pdf p.9 states the structure. |
| SCH-01 | Verified | ✓ | ✓ | – | tpl lock-file hash test. |
| SCH-02 | Verified | ✓ | ✓ | – | tpl schema test. |
| SCH-03 | Verified | ✓ | ✓ | – | Project schema; api round trip. |
| SCH-04 | Verified | ✓ | ✓ | – | Zod discriminated union; api rejects an unknown layer type. |
| SCH-05 | Verified | ✓ | ✓ | ✓ | All 8 layer types are created through the UI: panel fill, artwork, pattern, stitching, embellishment and hardware in the demo; texture and annotation (note) in `e2e: editing › note and texture`, which also checks the note reaches the PDF callouts. |
| SCH-06 | Verified | ✓ | ✓ | – | Schema; e2e editing (lock, rename, order via keyboard). |
| SCH-07 | Verified | ✓ | ✓ | ✓ | demo "Reopened project identical to saved state" in a fresh browser context. shots `13/14-reopened`. |
| EDT-01 | Verified | ✓ | ✓ | ✓ | shots. |
| EDT-02 | Verified | ✓ | ✓ | ✓ | demo front/back checks. |
| EDT-03 | Verified | ✓ | ✓ | ✓ | shots `15/16-realistic`. |
| EDT-04 | Verified | ✓ | ✓ | – | e2e workflow undo/redo is saved and reloaded. |
| EDT-05 | Verified | ✓ | ✓ | ✓ | `save-status` element waited on in every e2e step. |
| EDT-06 | Verified | ✓ | ✓ | ✓ | Drag, select, delete; Ctrl/⌘+D duplicate is implemented but has no dedicated e2e. Zoom/pan are manual-checked only. |
| EDT-07 | Verified | ✓ | ✓ | ✓ | e2e editing: inline rename (button, F2, Escape cancels), reorder buttons, lock/visibility. |
| EDT-08 | Verified | ✓ | – | ✓ | Labels such as "Add logo", "Add rhinestones", "Erase from this pattern". |
| EDT-09 | Verified | ✓ | ✓ | ✓ | Parts is the default tab; Layers tab used in e2e. |
| EDT-10 | Verified | ✓ | ✓ | ✓ | demo recolor checks on all garments. |
| EDT-11 | Verified | ✓ | ✓ | ✓ | demo hoodie (hood) and sweatpants (waistband) back-only overrides; pdf p.3 "front: Optic white; back: Clay". |
| ART-01 | Verified | ✓ | ✓ | ✓ | api upload tests (PNG + SVG); demo uploads SVG. |
| ART-02 | Verified | ✓ | ✓ | ✓ | demo drag; e2e editing keyboard move/resize/rotate; handles tested in session 1. |
| ART-03 | Verified | ✓ | ✓ | – | unit aspect test; e2e editing aspect ratio held. |
| ART-04 | Verified | ✓ | – | ✓ | Opacity slider (manual). |
| ART-05 | Verified | ✓ | – | ✓ | Layer order buttons (manual). |
| ART-06 | Verified | ✓ | ✓ | ✓ | e2e workflow clip-path + hit test; purple clip outline in shot `tshirt/05`. |
| ART-07 | Verified | ✓ | ✓ | ✓ | demo 24 × 18 cm entered; pdf p.5. |
| ART-08 | Verified | ✓ | ✓ | ✓ | demo anchor, reference and offsets; pdf p.5 placement sentence. |
| ART-09 | Verified | ✓ | ✓ | ✓ | demo screen print / embroidery. |
| ART-10 | Verified | ✓ | ✓ | ✓ | demo artwork ID VT-ART-01; pdf p.5. |
| ART-11 | Verified | ✓ | ✓ | – | PNG stored byte-for-byte. SVG stored as the sanitised copy; scripts and external references are removed by design. |
| ART-12 | Verified | ✓ | ✓ | – | sanitize tests (scripts, handlers, external refs, DTD, clean file → 0 removals). |
| ART-13 | Verified | ✓ | – | ✓ | Panel checkboxes, with a "spans N panels" note. No dedicated multi-panel automated test. |
| PAT-01 | Verified | ✓ | ✓ | ✓ | demo uploads a tile; shot `tshirt/06`. |
| PAT-02 | Verified | ✓ | ✓ | ✓ | Repeat width, rotation, offsets, opacity, panels in shot `06`. |
| PAT-03 | Verified | ✓ | ✓ | ✓ | 10 procedural textures; visible in realistic shots (knit, fleece). |
| PAT-04 | Verified | ✓ | – | ✓ | Per-component texture layer or material texture. |
| PAT-05 | Verified | ✓ | – | ✓ | Scale/strength sliders (manual). |
| PAT-06 | Verified | ✓ | – | – | Texture layer `materialId`, plus the material's own `textureId`. |
| PAT-07 | Verified | ✓ | ✓ | ✓ | demo "Erase affects only the pattern layer" (7 other layers byte-identical). |
| PAT-08 | Verified | ✓ | ✓ | – | Erase/restore tools; restore mode is not separately asserted in tests. |
| PAT-09 | Verified | ✓ | ✓ | ✓ | Same as PAT-07; the garment fill remains visible under erased areas. |
| PAT-10 | Verified | ✓ | ✓ | – | e2e workflow "Reset erased areas". |
| DEC-01 | Verified | ✓ | ✓ | ✓ | demo stitching on chosen seams; e2e "Stitching on the intended seams". |
| DEC-02 | Verified | ✓ | ✓ | ✓ | Thread color and style; pdf p.9. |
| DEC-03 | Verified | ✓ | ✓ | ✓ | Notes in pdf p.9 and callouts p.2. |
| DEC-04 | Verified | ✓ | – | ✓ | UI and PDF say "illustrative". |
| DEC-05 | Verified | ✓ | ✓ | ✓ | demo: 3 individual stones, 4 studs. |
| DEC-06 | Verified | ✓ | ✓ | ✓ | demo path + **point insertion**; e2e editing insert/remove/drag. Seam snapping is not implemented (separate enhancement). |
| DEC-07 | Verified | ✓ | ✓ | ✓ | Diameter and per-path spacing; count changes with path length (e2e editing). |
| DEC-08 | Verified | ✓ | – | ✓ | Finish select. |
| DEC-09 | Verified | ✓ | ✓ | ✓ | Attachment shown in BOM/pdf. |
| DEC-10 | Verified | ✓ | ✓ | ✓ | demo counts match on all 3 garments (26, 53, 72 stones; 4 studs each). |
| DEC-11 | Verified | ✓ | ✓ | – | Stored as points and paths; re-editable. |
| DEC-12 | Verified | ✓ | – | ✓ | 8 catalogue items. |
| DEC-13 | Verified | ✓ | ✓ | ✓ | demo placement and keyboard resize (size 40 → 40.8 mm). |
| DEC-14 | Verified | ✓ | ✓ | ✓ | Counted hardware BOM row on all garments. |
| DEC-15 | Verified | ✓ | ✓ | ✓ | "Visual placement only" callout (shot `tshirt/08`). |
| MEA-01 | Verified | ✓ | ✓ | – | Canvas units are converted through calibration. |
| MEA-02 | Verified | ✓ | ✓ | – | unit drift tests. |
| MEA-03 | Verified | ✓ | ✓ | ✓ | demo: cm and fractional-inch entry stored exactly (7 5/16″ = 185.7375 mm); shots `10/11`. |
| MEA-04 | Verified | ✓ | ✓ | ✓ | pdf p.6–8, measurement CSV. |
| MEA-05 | Verified | ✓ | – | ✓ | Base size and size range controls (manual). |
| MEA-06 | Verified | ✓ | ✓ | ✓ | e2e unconfirmed badge; demo shot `09`. |
| MEA-07 | Verified | ✓ | ✓ | ✓ | demo placement fields; pdf p.5. |
| MEA-08 | Verified | ✓ | ✓ | ✓ | "Visual estimate" badge; review export blocked until entered (unit + session 1 e2e). |
| MEA-09 | Verified | ✓ | ✓ | – | unit: other sizes empty; no grading code. |
| MEA-10 | Verified | ✓ | – | ✓ | Notice on the Measurements screen and pdf p.8. |
| GHO-01 | **Partial** | ✓ | ✓ | ✓ | Uses mesh, shadow, highlight and displacement maps. Panel masks come from template geometry. The `occlusion` and `foregroundComponents` manifest fields are unused. Assets are procedural. |
| GHO-02 | Verified | ✓ | – | ✓ | Pipeline order is in the code and in `TEMPLATE_AUTHORING.md`; realistic shots. |
| GHO-03 | **Partial** | ✓ | – | ✓ | Artwork gets fabric texture, shading and displacement. In flat chest regions the logo still reads as printed flat (2× crop of `VT-TS-001_R1_mockup_front.png`). |
| GHO-04 | Verified | ✓ | – | ✓ | Distinct print, embroidery, stone and stud treatments (hoodie embroidery, sweatpants studs). DTG shares the print treatment. |
| GHO-05 | **Partial** | ✓ | ✓ | ✓ | A convincing photographic T-shirt render has **not** been demonstrated. Kept incomplete by design. |
| GHO-06 | Verified | ✓ | – | ✓ | UI badge "procedural shading assets"; asset spec in the brief. |
| GHO-07 | Verified | ✓ | ✓ | ✓ | Flats and PDF don't depend on the renderer. |
| CMB-01 | Verified | ✓ | ✓ | ✓ | Palette table, pdf p.3. |
| CMB-02 | Verified | ✓ | – | ✓ | Disclaimers on every PDF page; no codes are generated. |
| CMB-03 | Verified | ✓ | ✓ | ✓ | demo completes materials; pdf p.4. |
| CMB-04 | Verified | ✓ | ✓ | ✓ | BOM table / CSV columns. |
| CMB-05 | Verified | ✓ | ✓ | ✓ | demo "Fabric consumption not inferred" (quantity type missing). |
| CMB-06 | Verified | ✓ | ✓ | ✓ | `counted` vs `entered` / `not entered` in BOM, pdf and CSV. |
| CMB-07 | Verified | ✓ | ✓ | ✓ | unit colorway test (color and material substitution, BOM per colorway). The demo seed's second colorway was shown in a session-1 screenshot. The verification runs used one colorway each. |
| TPK-01 | Verified | ✓ | ✓ | ✓ | 3 PDFs, R1 each. |
| TPK-02 | Verified | ✓ | ✓ | ✓ | p.1 for each garment. |
| TPK-03 | Verified | ✓ | ✓ | ✓ | p.2 callouts; stitching callout names fixed. |
| TPK-04 | Verified | ✓ | ✓ | ✓ | p.3. |
| TPK-05 | Verified | ✓ | ✓ | ✓ | p.4 (overlap fixed). |
| TPK-06 | Verified | ✓ | ✓ | ✓ | p.5. |
| TPK-07 | Verified | ✓ | ✓ | ✓ | p.6. |
| TPK-08 | Verified | ✓ | ✓ | ✓ | p.8. Inch entries print in the display unit, rounded to 0.01 cm. |
| TPK-09 | Verified | ✓ | ✓ | ✓ | p.9; close-up detail views fixed. |
| TPK-10 | Verified | ✓ | ✓ | ✓ | Labels page appears only when labels are specified (seed demo, api test); omitted for the verification styles, which have none. |
| TPK-11 | Verified | ✓ | ✓ | ✓ | p.10. |
| TPK-12 | Verified | ✓ | ✓ | ✓ | api test plus 33/33 pages show style, revision and "Page n of N". |
| TPK-13 | Verified | ✓ | ✓ | ✓ | Vector flats; text-overlap and text-bounds checks; manual review. |
| TPK-14 | Verified | ✓ | ✓ | ✓ | `*_measurements.csv` ×3. |
| TPK-15 | Verified | ✓ | ✓ | ✓ | `*_BOM.csv` ×3; formula-injection guard. |
| TPK-16 | Verified | ✓ | ✓ | ✓ | `*_mockup_front/back.png` ×3 at 2×. They are procedural-quality mockups. |
| TPK-17 | Verified | ✓ | ✓ | ✓ | api draft export lists open items; seed PDF "Open items" page. |
| TPK-18 | Verified | ✓ | ✓ | ✓ | Review blocked until required checks pass (api, e2e); all 3 verification styles issued as review. |
| TPK-19 | Verified | ✓ | ✓ | ✓ | api asserts no "manufacturer approved"; footer disclaimer. |
| TPK-20 | Verified | ✓ | ✓ | ✓ | unit: optional sections don't block; Tech Pack screen lists required items (shot `17`). |
| TPK-21 | Verified | ✓ | ✓ | – | See OUT-06. |
| SCR-01 | Verified | ✓ | ✓ | ✓ | e2e projects test (create, open, duplicate, collection grouping); archive/restore manual. |
| SCR-02 | Verified | ✓ | ✓ | ✓ | shot `tshirt/01-choose-garment`. |
| SCR-03 | Verified | ✓ | ✓ | ✓ | shots. |
| SCR-04 | Verified | ✓ | ✓ | ✓ | shots `09–11`. |
| SCR-05 | Verified | ✓ | ✓ | ✓ | shot `12-bom`. |
| SCR-06 | Verified | ✓ | ✓ | ✓ | shots `17/18`; page preview (session 1). |
| SCR-07 | **Partial** | ✓ | ✓ | ✓ | axe scan: 0 serious/critical on 14 states. Keyboard: tabs, lists, inline rename, move/resize/rotate of selected items. **Limitations:** no manual screen-reader audit; placing stones, drawing paths and erasing need a pointer; moderate/minor axe findings are not gated. |
| SCR-08 | Verified | ✓ | ✓ | ✓ | `verification/small-screen/*` at 390 px, 0 overflow. Editing on a phone is cramped but usable for review. |
| VER-01 | Verified | ✓ | ✓ | ✓ | demo + e2e + unit. |
| VER-02 | Verified | ✓ | ✓ | ✓ | demo front/back + overrides. |
| VER-03 | Verified | ✓ | ✓ | ✓ | demo reopen; api upload round trip. |
| VER-04 | Verified | ✓ | ✓ | ✓ | e2e hit test after drag. |
| VER-05 | Verified | ✓ | ✓ | ✓ | demo + e2e. |
| VER-06 | Verified | ✓ | ✓ | – | e2e undo, save, reload. |
| VER-07 | Verified | ✓ | ✓ | ✓ | demo + unit. |
| VER-08 | Verified | ✓ | ✓ | ✓ | e2e + PDF † / * markers. |
| VER-09 | Verified | ✓ | ✓ | ✓ | demo on 3 garments. |
| VER-10 | Verified | ✓ | ✓ | ✓ | demo on 3 garments plus snapshot. |
| VER-11 | Verified | ✓ | ✓ | – | unit + api. |
| VER-12 | Verified | ✓ | ✓ | ✓ | Automated checks plus 33 pages viewed. |
| VER-13 | Verified | ✓ | ✓ | – | demo + api. |
| VER-14 | Verified | ✓ | ✓ | – | api: missing blob → actionable 422; failed export rows offer retry (not forced in a test). |
| VER-15 | Verified | ✓ | ✓ | – | 52 unit/integration and 12 e2e tests. |
| CMP-01..06 | Verified | ✓ | ✓ | ✓ | demo on all three garments. |
| CMP-07 | **Partial** | ✓ | ✓ | ✓ | Realistic previews render for all garments with procedural assets. Photographic quality is not demonstrated. |
| CMP-08 | Verified | ✓ | ✓ | ✓ | demo cm and inch entry. |
| CMP-09 | Verified | ✓ | ✓ | ✓ | demo materials, BOM, notes; unit colorways. |
| CMP-10 | Verified | ✓ | ✓ | ✓ | `verification/*/` PDF, CSV and PNG exports. |
| CMP-11 | Verified | ✓ | – | ✓ | README setup; seeded demo projects. |

## Known limitations

1. **Photographic mockups are not done** (GAR-11, GHO-01/03/05, CMP-07). The renderer also needs two
   additions before photo assets can be used: file-based per-component masks and occlusion masks, and
   a mesh-registration helper. See `ASSET_ACQUISITION_BRIEF.md` §1.
2. **Accessibility** has passed an automated scan only. Placing stones, drawing paths and erasing need
   a pointer.
3. **Seam snapping** for paths is not implemented. It's a separate enhancement, not part of V1.
4. **Inch entries** print in cm rounded to 0.01 when the display unit is cm. Stored values are exact.
5. **Flats and POM defaults** are nominal size-M drawings, not production patterns. A technical
   designer should review them before production use.
6. **Single-user and local:** no accounts or hosting. Stored uploads are never deleted, which keeps
   revisions safe; no clean-up has been built.
7. Ctrl/⌘+D, zoom/pan, archive/restore and restore-mode erasing have **no dedicated automated tests**.
   They were exercised manually.

## Follow-up work (separate from V1)

- Hosting, team accounts, cloud storage and database.
- More garments.
- Automatic clean-up of unused uploaded files. Uploads are retained; nothing is deleted.
- Seam snapping and keyboard-only path drawing.
- Renderer support for file-based masks and occlusion, plus a mesh-registration helper (needed
  before photographic assets).

## Continuation note

- **State:** V1 functionality is verified except the photographic-mockup requirement.
  The current work is on branch `claude/eloquent-darwin-11wj00`.
- **To re-verify everything:**
  1. `npm run typecheck && npm test && npm run test:e2e`. The demo spec rewrites `verification/`.
  2. `npx tsx scripts/pdf-bounds.mts <pdf>`.
  3. Start `npm run dev`, then run `node scripts/small-screen-check.mjs http://localhost:5173 <projectId> verification/small-screen`.
- **Next steps:**
  1. Choose an asset route from the brief.
  2. Implement file-based masks and occlusion plus the registration helper.
  3. Install a v2 template asset set for the T-shirt.
  4. Demonstrate it with real artwork, then repeat for the hoodie and sweatpants.
