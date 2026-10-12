# Ghost-mockup asset acquisition brief

**Goal:** a convincing garment, with artwork integrated into its folds, texture, shadows and
highlights, for the Boxy T-shirt, Pullover hoodie and Straight-leg sweatpants (front + back).

**Status:** **incomplete.** The renderer works, but its current assets are procedurally drawn
(`procedural-v1`). In the 2× export the knit texture shows through prints, but a chest logo sits
flat: there are no folds where it is placed (see `verification/tshirt/VT-TS-001_R1_mockup_front.png`).
This requirement stays incomplete until a photographic or rendered asset set has been installed and
the result has been shown with real artwork.

Nothing has been purchased, and no paid service has been added.

---

## 1. What the current renderer actually consumes

Source: `src/client/render/ghost.ts` and `ghostViewAssetsSchema` in `src/shared/schema/template.ts`.
These are the facts that any asset set has to fit.

| Manifest field | Used today? | What it must be |
|---|---|---|
| `width`, `height` | yes | Mockup canvas size at 1×. The app renders previews at 1×, tech-pack PNGs at 2× and downloads at 3×. Current sizes: T-shirt 1000×880, hoodie 1000×820, sweatpants 760×1000. |
| `mesh` (`cols`, `rows`, `bounds`, `dst[]`) | yes | Technical-to-mockup mapping. A regular grid over the view's `viewBox` (`bounds` must equal it), plus the mockup-pixel (1×) position of every vertex, row-major. Panel colours, patterns, artwork, stitching and stones are all warped through it. |
| `shadow` (URL) | yes | Grayscale image, **white = unshaded**. Multiplied over the garment only. Any browser image format; it is scaled to the canvas. |
| `highlight` (URL) | yes | Grayscale on **black = no change**. Screen-blended at 85% over the garment. |
| `displacement` (URL) | yes | Grayscale, **mid-gray (128) = no displacement**. Its local gradient shifts printed artwork by up to ~60 px×scale, and raised artwork (embroidery etc.) by ~45 px×scale. |
| `occlusion` (URL / null) | **no** | Declared but ignored. Today occlusion comes from the template panels' z-order. |
| `foregroundComponents` | **no** | Declared but ignored. |
| Panel masks | — | **Not read from files.** They are rasterised from the template's vector panels and warped through the mesh. |

### Consequence for photographic assets
Because the panel colour masks come from the template, **the garment silhouette in a photo must
coincide with the warped template outline**. Within about 2 px at 1× is fine. A larger mismatch
puts fill colour on the background or leaves gaps.

Getting there needs one of two things:
- **(a)** a very careful mesh registration, or
- **(b)** a small renderer change, **not built yet**, so it accepts:
  - per-component mask images, e.g. `front-mask-sleeve_left.png`;
  - a real occlusion mask (hood edge over the body, pocket lip, drawcords).

**Recommendation:** do (b) before installing any photographic set. It's a contained change (a few
optional manifest fields plus one branch in the renderer), and you could do it after choosing an
asset source.

A **mesh-registration helper** is also missing. It would let you drag control points onto a photo
and save the `dst[]` grid. Today the grid is generated from code in `scripts/ghost/specs.ts`.

---

## 2. Exact deliverables per garment

Per template version, for each of the **front** and **back** views:

| File (in `public/ghost/<template>-v<N>/`) | Format | Resolution (3× of mockup) | Content |
|---|---|---|---|
| `<view>-shadow.png` | 8- or 16-bit grayscale PNG | T-shirt 3000×2640 · hoodie 3000×2460 · sweatpants 2280×3000 | Shading only, white = none. No print, labels, lint or background. |
| `<view>-highlight.png` | same | same | Sheen and specular highlights only, on black. |
| `<view>-displacement.png` | same | same | Low-frequency fold relief, 128 = flat. Blur ≈ 1–2% of width so text stays legible. |
| `<view>-mask-<componentId>.png` *(needs renderer change b)* | 8-bit alpha PNG | same | One mask per template component visible in that view, using the exact ids below. |
| `<view>-occlusion.png` *(needs renderer change b)* | 8-bit alpha PNG | same | Parts that sit in front of other parts in the photo. |
| Manifest JSON (`src/shared/templates/ghost/<template>-v<N>.json`) | JSON | — | `width`/`height` at 1×, a registered `mesh` (≥ 20×20 grid recommended), and the file URLs above. |

**Component ids per view** (masks must use these names):

- **T-shirt, front:** `body_front`, `sleeve_left`, `sleeve_right`, `neck_rib`, and `body_back` for the
  inside of the back neck.
- **T-shirt, back:** `body_back`, `sleeve_left`, `sleeve_right`, `neck_rib`.
- **Hoodie, front:** `body_front`, `sleeve_left`, `sleeve_right`, `cuff_left`, `cuff_right`, `hem_rib`,
  `kangaroo_pocket`, `hood`, `hood_lining`, `drawcord`.
- **Hoodie, back:** `body_back`, `sleeve_left`, `sleeve_right`, `cuff_left`, `cuff_right`, `hem_rib`, `hood`.
- **Sweatpants, front:** `leg_front_left`, `leg_front_right`, `waistband`, `drawcord`.
- **Sweatpants, back:** `leg_back_left`, `leg_back_right`, `waistband`, `back_pocket`.

**Orientation:** front views show the wearer's **right** on the viewer's **left**. Left and right are
always named from the wearer's side.

**Alignment and proportion:**
- The photographed or rendered garment must match the template's base size **M** proportions, as
  given in the template defaults (e.g. tee: 700 mm HPS length, 592 mm chest).
- Shoot or render square-on with minimal perspective: a long lens (≥ 85 mm equivalent) and the
  camera axis at mid-chest.
- Front and back must be framed identically: same scale and same position of the high-point
  shoulder and hem.

**Base garment colour:** a light neutral (about 20–30% gray, or a light heather). Pure white clips
the highlights; black hides the shading. The app recolours each panel itself, so the photo's own
colour is discarded.

**Versioning:** install the set as a **new template version** (e.g. `tshirt-boxy@2`), so existing
projects keep v1. Then run `npm run lock:templates` and `npm test`.

---

## 3. Acquisition routes

### A. Existing licensed ghost-mockup assets (PSD/PNG packs)

**Licence must explicitly allow:**
1. **Commercial use.**
2. **Use inside a software application that renders end-user designs.** Many stock mockup licences
   forbid "mockup generators", "print-on-demand tools" or "templates for resale". This is the clause
   that usually blocks use; look for an *extended*, *app* or *SaaS* licence.
3. **Derivative works.** The maps are extracted from the file.
4. **Distribution with the application.** If this repository stays public (it is your GitHub
   profile repository), licensed files **must not be committed** unless the licence permits
   redistribution. Keep them in a private asset pack loaded from a local path instead.
5. **No attribution requirement** that conflicts with how images are exported, or a way to meet it.

Keep the licence text and the invoice with the asset pack.

**Fit with the app:** pick garments whose cut matches the templates: a dropped-shoulder boxy tee,
a relaxed pullover hoodie with a kangaroo pocket, and straight-leg sweatpants with elastic waist
and drawcord. Front and back must come from the same garment and shoot.

**Can PSD files be converted? Yes, partly.**

What converts directly, with free tools (Photopea, GIMP, or the `psd-tools` Python / `ag-psd` npm
libraries):
- **Shadow and highlight layers** (usually *Multiply* and *Screen* layers): export each as
  grayscale PNG. Normalise so the shadow layer's unshaded areas are white and the highlight
  layer's empty areas are black.
- **Displacement map:** often shipped as a separate `.psd`. If not, derive one from a blurred
  grayscale copy of the base photo.
- **Garment silhouette:** from the colour-overlay layer mask or a clipping path. **Per-part masks**
  (sleeves, ribs, pocket) are rarely included and must be painted by hand.

What does not convert:
- **Smart-object placement and warps** (perspective, mesh warp, displace filter). These live in
  Photoshop-specific data and do **not** turn into the app's mesh. The `dst[]` grid has to be
  re-registered against the photo by hand, or with the helper tool described in §1.

### B. Commissioned photography or garment renders

**Photography (ghost mannequin), per garment:**
- **Sample:** base size M, made to the template proportions, in a light neutral fabric that matches
  production (jersey for the tee, fleece for the hoodie and sweatpants). Lint-free and steamed,
  with no visible labels.
- **Shots:**
  - Front and back on the invisible mannequin.
  - The inside back neck, for the neck composite.
  - For the hoodie, the hood up, with the hood interior lit.
  - For the sweatpants, the waistband relaxed.
- **Camera:**
  - Tripod-locked, with the same distance, height and focal length (85–105 mm) for both views.
  - Tethered RAW, ≥ 6000 px on the long side, with a colour checker in a reference frame.
  - Diffuse, even key light with soft fill. No hard specular hot spots and no coloured spill.
- **Deliverables:**
  - Retouched 16-bit TIFFs on a plain background.
  - A layered PSD with one named mask per component id from §2, plus an occlusion mask.
  - The usage rights listed in §3A (with full ownership or an exclusive licence to you, if possible).

**3D garment renders, as a commissioned alternative.** A 3D artist can drape the garment in
industry 3D software and deliver **2D render passes**. The app stays 2D, as V1 requires. Passes:
- a flat-lit albedo pass (white);
- an ambient-occlusion / shading pass, which becomes the shadow map;
- a specular pass, which becomes the highlight map;
- a normal or height pass, which becomes the displacement map;
- **object-ID masks per component**, which give exact masks;
- optionally a UV or position pass. This would allow better artwork mapping than the mesh, but it
  needs renderer work.

Renders give perfectly consistent front and back views and exact masks. Their realism depends on
the artist and the fabric simulation.

### C. Generated images for prototyping only

AI image generators can produce plausible ghost-mockup photos for **look-development**. Limits:
- **Consistency:**
  - Front and back are not the same garment.
  - Proportions won't match the templates, so the mesh can't be registered cleanly.
  - Seams, neckline, rib heights and pocket shapes drift or are invented.
- **No real per-part masks or passes.** They must be hand-painted.
- **Rights:** ownership and commercial-use terms depend on the tool. Some outputs may not be
  protectable.
- **Integrity:** generative AI must not become a runtime dependency (TEC-09). Generated files could
  only be static prototype assets, labelled as such in the manifest.

Use this route to judge the look, not as the production asset set.

---

## 4. Acceptance test for "convincing photographic mockup"

The requirement can be marked complete only when:
1. Asset sets for all three garments, front and back, are installed as new template versions, and
   the template and e2e test suites pass.
2. With real logos on the chest and back, printed artwork visibly follows the folds (displacement),
   picks up the photographed shading and highlights, and shows fabric texture, at 2× export size.
3. Panel colours stay inside their panels within 2 px at 1×, with no background bleed or gaps.
   Hood, pocket and rib occlusion is correct.
4. Embroidery, rhinestone and stud previews still read as distinct treatments.
5. Side-by-side screenshots and exports are reviewed and approved by you.
