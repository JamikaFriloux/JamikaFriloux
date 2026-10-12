# Template authoring

How garment templates and their ghost-mockup rendering assets are structured, and how to add or
revise one. Schemas: `src/shared/schema/template.ts`. Examples: `src/shared/templates/*.ts`.

## 1. Principles

- **Templates are immutable and versioned.** Projects store `{ id, version }` and always resolve to exactly
  that geometry. `src/shared/templates/published-lock.json` holds a SHA-256 of every published version and the
  test suite fails if one changes. To change geometry, measurements, anchors or ghost manifests, add a new
  version (e.g. `tshirtBoxyV2`), keep v1 in the registry for existing projects, then run
  `npm run lock:templates` (it refuses to overwrite an existing lock entry).
- **Design data never lives in templates.** Colors, materials, artwork, measurements values, etc. belong to
  the project. Templates only provide structure.
- **Structure is explicit.** `structure.closure` / `structure.features` describe construction. Decorations
  (including the “Decorative zipper” hardware) never alter it; a zip hoodie would be a separate template.
- **No invented numbers.** POM `defaultMm` is the value *as drawn* at the base size and is always shown as an
  unconfirmed default. Use `null` when a value cannot be read from a drawing (e.g. extended waist). Never
  add other sizes or grade rules to a template.

## 2. Coordinate system and calibration

- Each view has its own `viewBox` `[minX, minY, width, height]` in template units; y points down.
- All V1 templates use `calibration = { kind: 'nominal-drawing-scale', mmPerUnit: 1, baseSize: 'M' }`:
  1 unit = 1 mm *for the drawn base size*. This lets the editor estimate placement from the canvas; such
  values are labelled “visual estimate” until the user enters manufacturing dimensions. A template with
  `calibration: null` is treated as visual-only (canvas edits never touch physical values).
- Front views show the wearer’s **right** side on the viewer’s **left**; back views the opposite. Name
  components from the wearer’s perspective (`sleeve_left` = wearer’s left).
- Author one side and mirror it with `mirrorPath(d)` (mirrors about x = 500, so keep views symmetric about
  x = 500). Paths must use **absolute** `M L C Q Z` commands only (`parsePath` rejects relative commands and
  arcs; use `circlePath()` for circles).

## 3. Template fields

| Field | Purpose |
|---|---|
| `id`, `version`, `name`, `category`, `description` | Identity. |
| `structure` | Construction facts shown in the editor and tech pack. |
| `sizes` | `available`, `defaultBase`, `defaultRange`. |
| `calibration` | See above. |
| `components[]` | Named parts **shared across views** (`id` is the link). `group`, `materialRole` (`shell`/`rib`/`lining`/`trim` → default material), `decorationMethods` (validated on export). |
| `views[].panels[]` | Closed paths; each references a `componentId`, has a draw order `z`, and `side` (`outer` or `inner` — the inside of the garment seen through an opening, e.g. the back neck). Panels double as **clip paths**: decorations are clipped per panel and occluded by higher-`z` panels. |
| `views[].seams[]` | Open paths that stitching layers style. Same seam `id` in both views = same seam. `defaultStyle` drives the default flat drawing. |
| `views[].details[]` | Non-selectable linework: rib lines, eyelets, aglets, creases. |
| `views[].anchors[]` | Placement reference points (must lie inside a panel of their `componentId` — tested). Their `description` is printed in the tech pack. |
| `views[].measurementLines[]` | POM diagram lines; the drawn length must match `defaultMm` within 3 mm at nominal scale (tested). |
| `poms[]` | `code`, `label`, `howToMeasure`, `view`, `defaultMm` (or `null`), default tolerances. |
| `ghost` | Ghost-mockup asset manifest (below) or `null` if none is installed. |

## 4. Ghost-mockup rendering assets

The renderer (`src/client/render/ghost.ts`) is a deterministic 2D pipeline. For each view a template
provides (`ghostViewAssetsSchema`):

| Asset | Format | Meaning |
|---|---|---|
| `width`, `height` | px at 1× | Mockup canvas size. |
| `mesh` | `{cols, rows, bounds, dst[]}` | **Technical → mockup mapping.** A regular grid over `bounds` (must equal the view’s `viewBox`) and the mockup-space position of each vertex (row-major). Rendered as piecewise-affine triangles; also used to place embellishment glints. |
| `shadow` | grayscale image, white = no change | Multiplied over the garment (folds, creases, hem roll). |
| `highlight` | grayscale image on black | Screen-blended (crests, shoulder/chest light). |
| `displacement` | grayscale, mid-gray = none | Its gradient displaces printed/embroidered artwork so graphics bend with folds. |
| `occlusion` | optional mask | Reserved for photographic sets; procedural sets derive occlusion from the z-ordered panel id-map. |
| `foregroundComponents` | component ids | Parts that sit in front (hood, pocket, rib). |

Generated at render time from template geometry (so they always match): **neutral garment base / panel
masks** (panel id-map rasterised from `views[].panels` in `z` order), **edge occlusion** (blurred
silhouette), **inner-garment shadow** (panels with `side: 'inner'`), and **fabric surface detail**
(seeded procedural tiles per curated texture — deterministic).

Pipeline order: panel colors (+ dyed all-over patterns) → warp through mesh → fabric texture per panel →
printed artwork (displaced, ink texture) → raised artwork (embroidery/appliqué/puff: contact shadow, thread
texture, edge light) → seams & stitching → edge occlusion, inner shadow, shadow map, highlight map →
embellishments & hardware with contact shadows and glints → studio backdrop.

### Current asset quality: `procedural-v1`

V1 assets are **hand-authored vector folds** defined in `scripts/ghost/specs.ts` in *technical*
coordinates, warped and rasterised by `npm run build:ghost` into `public/ghost/<template>-v<version>/` and a
JSON manifest in `src/shared/templates/ghost/`. They give convincing volume and fold cues but are **not
photographic**. Upgrading to photographic assets (`quality: 'photographic'`) requires, per garment & view:

1. A neutral (light-gray or white) ghost-mannequin photograph of a physical sample, ≥ 3000 px, shot square to
   camera with diffuse light; the garment must match the template’s base-size proportions.
2. Hand-registered **mesh** (≥ 20×20 control grid) mapping template coordinates onto the photo, so each panel
   lands on its photographed counterpart.
3. **Shadow map** = photo luminance divided by a flat-lit albedo estimate (white = unshaded), and a separate
   **highlight map** for specular/sheen; both cleaned of print/labels.
4. **Displacement map** from the shading low-frequency component (or a captured normal map).
5. **Occlusion masks** for parts that overlap in the photo (hood edge over body, pocket lip, drawcords).
6. Bump the template version, update the manifest, run the tests, and `npm run lock:templates`.

## 5. Adding a garment (checklist)

1. Create `src/shared/templates/<id>.ts` with components, front/back views, seams, details, anchors,
   measurement lines and POMs. Draw at nominal 1 mm/unit for the base size.
2. Register it in `src/shared/templates/index.ts`.
3. Add a ghost spec in `scripts/ghost/specs.ts`, run `npm run build:ghost`, and reference the generated JSON
   from the template (`ghost: ghostAssets`). Or set `ghost: null` — the UI then states that only the technical
   view is available.
4. `npm test` — the template suite checks schema validity, path parsing, shared component ids, anchor
   containment, POM line lengths vs. defaults, mesh completeness and project creation.
5. `npm run lock:templates` to publish.
6. Optionally add demo content in `src/server/demo/seed.ts`.
