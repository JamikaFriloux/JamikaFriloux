# Verification evidence (session 2)

Everything in this folder was produced by running the real application. The three garment
folders are written by `npx playwright test e2e/demo.spec.ts`, which drives the UI in Chromium and
saves screenshots and downloaded exports. `results.json` lists every recorded check: 54 / 54 passed.

## T-shirt — full demonstration (`tshirt/`)

| Step | Screenshot |
|---|---|
| Choose a garment | `01-choose-garment.png` |
| New style in the studio | `02-new-style-studio.png` |
| Recolor one panel (right sleeve → Forest) | `03-recolor-right-sleeve.png` |
| Upload and drag a logo (visual estimate) | `04-logo-dragged.png` |
| Enter physical size, reference and offsets (24 × 18 cm, 5 cm below center chest, ± 0.5 cm) | `05-logo-placement-spec.png` |
| Pattern on the left sleeve, partly erased (other layers unchanged) | `06-pattern-erased.png` |
| Rhinestone path with an inserted point + individual stones | `07-rhinestones.png` |
| Studs and a metal badge (adjusted by keyboard) | `08-studs-hardware.png` |
| Measurements: defaults in cm → entered → inches → back to cm | `09-…`, `10-measurements-inches.png`, `11-measurements-cm.png` |
| Materials assigned; BOM with counted items | `12-bom.png` |
| Reopened in a fresh browser (front/back) | `13-reopened-front.png`, `14-reopened-back.png` |
| Realistic preview (procedural assets) | `15-realistic-front.png`, `16-realistic-back.png` |
| Completeness checks; revision R1 exported | `17-techpack-checks.png`, `18-revision-exported.png` |

**Exports (revision R1, "ready for manufacturer review"):** `VT-TS-001_R1_techpack.pdf`,
`VT-TS-001_R1_BOM.csv`, `VT-TS-001_R1_measurements.csv`, `VT-TS-001_R1_mockup_front.png`,
`VT-TS-001_R1_mockup_back.png`.

## Hoodie (`hoodie/`) and sweatpants (`sweatpants/`)

Each run covers:
- an independent part recolor, plus a **back-only** override (hood / waistband);
- a logo with physical placement, and stitching on chosen seams;
- a rhinestone path, studs and hardware;
- all POMs entered and confirmed;
- completed materials plus an alternate material on one part;
- reopen, realistic preview, and review export.

The checks confirm:
- embellishment counts (hoodie 53 stones, sweatpants 72; 4 studs each);
- material references in the BOM;
- the front/back assignment;
- that the issued snapshot keeps all of these.

## Small screens (`small-screen/`)

All five screens at 390 px, from `scripts/small-screen-check.mjs`: 0 px horizontal overflow at the
page level and in the inner scroll container.

## Checks that could not be run here

- **Printed output.** PDFs were inspected on screen (rasterised at 75 dpi) and by automated
  text-bounds and overlap checks. Paper printing and colour accuracy were not tested.
- **Other PDF readers.** Rendering was checked with poppler and pdf.js only, not Acrobat, Preview or
  printer RIPs.
- **Other browsers.** Only Chromium was used. Firefox and Safari were not tested, so canvas
  compositing and SVG-filter rendering in the mockups may differ there.
- **Screen readers.** Accessibility was scanned automatically (axe-core). No assistive-technology
  user testing was possible.
- **Photographic mockups.** No photographic assets exist; see `../ASSET_ACQUISITION_BRIEF.md`.
