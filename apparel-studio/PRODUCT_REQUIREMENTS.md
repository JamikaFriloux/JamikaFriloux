# Product Requirements — Apparel Studio (V1)

Every requirement from the product brief, with a stable ID. IDs never change meaning; new
requirements get new IDs. Status for each ID is tracked in `PROGRESS.md`.

## WRK — Working method
| ID | Requirement |
|---|---|
| WRK-01 | Inspect existing project and preserve useful work (repo root `README.md` is a GitHub profile README and is left untouched; the app lives in `apparel-studio/`). |
| WRK-02 | Maintain PRODUCT_REQUIREMENTS.md, IMPLEMENTATION_PLAN.md, PROGRESS.md, TEMPLATE_AUTHORING.md and keep them updated. |
| WRK-03 | Work in verifiable phases: identify requirements, build, run checks, inspect UI, fix, update checklist. |
| WRK-04 | A feature is complete only when it works with saved project data (no placeholder buttons). |
| WRK-05 | Unavailable assets/services: implement what can work, document the missing dependency, mark incomplete. |
| WRK-06 | Keep a precise continuation note (phase, files, checks, open issues, next steps). |

## OUT — Product outcome
| ID | Requirement |
|---|---|
| OUT-01 | Workflow: create style → choose garment → customize parts → add artwork/decorations → ghost preview → measurements/manufacturing details → export tech pack. |
| OUT-02 | Visual design and tech pack share one source of truth (no separate tech-pack editor). |
| OUT-03 | Changing a panel's material updates its material reference in the BOM. |
| OUT-04 | Changing a logo's manufacturing dimensions updates its placement specification. |
| OUT-05 | Adding counted rhinestones updates their BOM quantity. |
| OUT-06 | Exporting a revision preserves an immutable snapshot of issued specifications. |

## TEC — Scope and technical approach
| ID | Requirement |
|---|---|
| TEC-01 | TypeScript + React with a suitable web framework; relational database; asset storage. |
| TEC-02 | Local development without paid services. |
| TEC-03 | Storage integrations replaceable (storage adapter interface). |
| TEC-04 | Precise SVG/vector garment templates for editing and technical drawings. |
| TEC-05 | Separate deterministic 2D rendering pipeline for ghost mockups. |
| TEC-06 | Structured, validated project data. |
| TEC-07 | Reliable PDF generation workflow. |
| TEC-08 | Excluded from V1: full 3D, automatic pattern drafting, fit simulation, AI garment geometry, automatic grading. |
| TEC-09 | No generative-AI dependency for the editor or authoritative mockup renderer. |

## GAR — Garment library
| ID | Requirement |
|---|---|
| GAR-01 | Boxy T-shirt template (implemented completely first). |
| GAR-02 | Pullover hoodie template using the same template system. |
| GAR-03 | Straight-leg sweatpants template using the same template system. |
| GAR-04 | Each garment: accurate, visually coherent front and back technical views. |
| GAR-05 | Individually selectable garment panels. |
| GAR-06 | Named garment components. |
| GAR-07 | Seam paths. |
| GAR-08 | Placement reference anchors. |
| GAR-09 | Measurement definitions and diagrams. |
| GAR-10 | Supported decoration methods per garment. |
| GAR-11 | Matched ghost rendering assets where available. |
| GAR-12 | No generic clothing blobs presented as professional templates. |
| GAR-13 | Hoodie and sweatpants can be grouped as a collection/set while keeping separate style specs and tech packs. |
| GAR-14 | Garment structure stays meaningful: decorative zipper artwork on a pullover never converts it to a zip hoodie. |

## SCH — Template and project schema
| ID | Requirement |
|---|---|
| SCH-01 | Immutable, versioned garment templates separate from editable design instances. |
| SCH-02 | Template: ID + version, category + name, view coordinate systems, panel geometry, component IDs shared across views, clipping paths, draw order, seam paths, measurement definitions, placement anchors, optional calibrated mockup mappings, rendering asset references. |
| SCH-03 | Project: identity, template ID + version, layers, uploaded assets, colorways + palette, materials, BOM, measurements by size, decoration specs, construction notes, labels & packaging, revisions & exports. |
| SCH-04 | Validated discriminated schemas for layer types (no unstructured property bags). |
| SCH-05 | Layer types: panel fill, artwork, pattern, texture, stitching, embellishment, hardware, annotation. |
| SCH-06 | Every relevant layer: stable ID, view reference, target panels/components, visibility, lock, stacking order, opacity, transform, optional mask/material/manufacturing references. |
| SCH-07 | Asset references and masks persist; reloading restores the entire design. |

## EDT — Design editor
| ID | Requirement |
|---|---|
| EDT-01 | Large center canvas; left panel (parts + add-design tools); right panel (selected-item settings). |
| EDT-02 | Front/back view switching. |
| EDT-03 | Technical / realistic preview switching. |
| EDT-04 | Undo and redo. |
| EDT-05 | Visible saving status. |
| EDT-06 | Zoom, pan, selection, deselection, duplication, deletion. |
| EDT-07 | Layer ordering, locking, visibility, naming. |
| EDT-08 | Approachable labels ("Add logo", "Change sleeve color", "Add pattern", "Add rhinestones", "Erase from this pattern"). |
| EDT-09 | Simple Parts view by default; Layers view for finer control. |
| EDT-10 | Changing one panel does not change the whole garment. |
| EDT-11 | Shared component assignments consistent across views, with an explicit way to create intentional per-view differences. |

## ART — Logos and graphics
| ID | Requirement |
|---|---|
| ART-01 | Upload transparent PNG and sanitized SVG artwork. |
| ART-02 | Move, resize, rotate. |
| ART-03 | Preserve aspect ratio. |
| ART-04 | Opacity. |
| ART-05 | Layer order. |
| ART-06 | Clip to selected panels. |
| ART-07 | Physical finished width and height. |
| ART-08 | Placement reference and offsets. |
| ART-09 | Decoration method. |
| ART-10 | Artwork notes and identifiers. |
| ART-11 | Source artwork kept intact; edits are not flattened. |
| ART-12 | Uploaded SVG treated as untrusted: sanitized, no scripts or unsafe external references. |
| ART-13 | A graphic may target multiple panels with explicit placement/clipping behavior. |

## PAT — Patterns, textures, erasing
| ID | Requirement |
|---|---|
| PAT-01 | Patterns from uploaded repeat tiles. |
| PAT-02 | Pattern scale, rotation, horizontal/vertical offset, opacity, panel clipping. |
| PAT-03 | Small curated texture library. |
| PAT-04 | Per-panel texture assignment. |
| PAT-05 | Adjustable texture appearance scale and strength. |
| PAT-06 | Texture links to the actual material specification where applicable. |
| PAT-07 | Erasing affects only the selected decoration layer via a persistent mask. |
| PAT-08 | Erase and restore behavior. |
| PAT-09 | Erasing a pattern never removes the garment, another logo, or the base color. |
| PAT-10 | Clear way to reset the selected layer's mask. |

## DEC — Stitching, rhinestones, studs, hardware
| ID | Requirement |
|---|---|
| DEC-01 | Stitching appearance applied to predefined seam paths. |
| DEC-02 | Stitch color and visual style. |
| DEC-03 | Separate stitching manufacturing notes. |
| DEC-04 | Illustrative dash pattern is not presented as a full construction spec. |
| DEC-05 | Rhinestones/studs placed individually. |
| DEC-06 | Rhinestones/studs repeated along an editable path. |
| DEC-07 | Adjustable diameter and spacing. |
| DEC-08 | Color or finish selection. |
| DEC-09 | Attachment method stored. |
| DEC-10 | Placed items counted for the BOM. |
| DEC-11 | Placements stay editable (not flattened). |
| DEC-12 | Small curated hardware set. |
| DEC-13 | Hardware placement, size, finish, notes. |
| DEC-14 | Hardware linked to BOM entries. |
| DEC-15 | Visual hardware placement clearly distinguished from structural garment changes. |

## MEA — Physical measurements and placement
| ID | Requirement |
|---|---|
| MEA-01 | Canvas pixels / SVG units are not manufacturing units. |
| MEA-02 | Decimal-safe canonical physical unit (millimetres) internally. |
| MEA-03 | cm/in display and input without cumulative conversion drift. |
| MEA-04 | Measurement: POM code, label, how-to-measure, diagram reference, values by size, +/- tolerances, source, confirmation status. |
| MEA-05 | Choose base size and size range. |
| MEA-06 | Template values marked as defaults until confirmed. |
| MEA-07 | Artwork placement: finished dimensions, reference anchor, H/V offsets, placement method, view + component, user tolerance. |
| MEA-08 | Calibrated mapping only where it exists; otherwise placement is labeled visual-only and explicit manufacturing dimensions are required before a manufacturer-review export. |
| MEA-09 | No invented measurements or grading rules. |
| MEA-10 | Measurement changes do not imply the mockup was refitted; V1 states it does not simulate fit or drape. |

## GHO — Ghost mockup rendering
| ID | Requirement |
|---|---|
| GHO-01 | Separate repeatable 2D renderer using matched assets: neutral base, panel masks, shadow map, highlight map, fabric surface detail, foreground occlusion masks, technical→mockup mapping, optional displacement/mesh mapping. |
| GHO-02 | Pipeline order: panel colors → textures/patterns → artwork mapping → folds/shadows/highlights preserved → foreground occlusion → stitching and decorations in correct order. |
| GHO-03 | Logos integrated with the garment, not pasted over all shading. |
| GHO-04 | Distinct appearance previews for screen print, embroidery, rhinestones, studs (labeled as appearance previews, not machine files). |
| GHO-05 | One convincing T-shirt render before expanding. |
| GHO-06 | If high-quality assets are missing: renderer built, asset spec documented, not presented as complete. |
| GHO-07 | Technical drawing output available independently of ghost rendering. |

## CMB — Colors, materials, BOM
| ID | Requirement |
|---|---|
| CMB-01 | Color: name, screen value, optional user-supplied standard system + code, approval status. |
| CMB-02 | No invented Pantone matches; screen colors do not guarantee fabric colors. |
| CMB-03 | Material: name, composition, weight + unit, finish, supplier + reference, notes. |
| CMB-04 | BOM: component, material/trim reference, quantity + unit, applicable colorways, supplier ref, notes, quantity type (counted/entered/estimated). |
| CMB-05 | No fabric consumption inferred from 2D drawings. |
| CMB-06 | Counted embellishments distinguishable from manually entered consumption. |
| CMB-07 | Colorways reuse the same style with explicit color and material substitutions. |

## TPK — Tech-pack output
| ID | Requirement |
|---|---|
| TPK-01 | Multipage PDF from a saved revision. |
| TPK-02 | Cover: style identity, revision, front/back overview. |
| TPK-03 | Technical flats with numbered callouts. |
| TPK-04 | Colorways and color references. |
| TPK-05 | Materials and BOM. |
| TPK-06 | Artwork dimensions, placement, application methods. |
| TPK-07 | Measurement diagrams. |
| TPK-08 | Size specification tables with tolerances. |
| TPK-09 | Construction notes and detail views. |
| TPK-10 | Labels and packaging when specified. |
| TPK-11 | Revision history. |
| TPK-12 | Style number, revision, page number on every page. |
| TPK-13 | Vector technical drawings where practical; tables paginate cleanly; readable; nothing clipped. |
| TPK-14 | Measurement CSV export. |
| TPK-15 | BOM CSV export. |
| TPK-16 | High-resolution mockup PNG when a supported render exists. |
| TPK-17 | Draft export permits incomplete specs and lists missing information. |
| TPK-18 | "Ready for manufacturer review" export requires applicable checks to pass. |
| TPK-19 | Never labeled manufacturer-approved; specs are for review, not sample approval. |
| TPK-20 | Incomplete required fields surfaced before export; optional unused sections do not block. |
| TPK-21 | Export from an immutable snapshot; later edits cannot change an issued revision. |

## SCR — Screens
| ID | Requirement |
|---|---|
| SCR-01 | Projects: create, open, duplicate, organize styles. |
| SCR-02 | Choose a garment: preview views, editable parts, rendering availability. |
| SCR-03 | Design Studio: all garment editing tools and preview controls. |
| SCR-04 | Measurements: interactive POM diagram beside the size table, units and tolerances. |
| SCR-05 | Materials & Colors: palette, materials, component assignments, BOM. |
| SCR-06 | Tech Pack: page preview, completeness checks, revision notes, exports. |
| SCR-07 | Polished accessible UI: readable controls, clear selection, helpful empty/error states. |
| SCR-08 | Desktop editing prioritized; small screens usable for reviewing project info. |

## VER — Required verification
| ID | Requirement |
|---|---|
| VER-01 | Recoloring a sleeve does not recolor the body. |
| VER-02 | Front/back component links behave correctly. |
| VER-03 | Uploaded artwork survives save and reload. |
| VER-04 | Artwork clipping correct after transforms. |
| VER-05 | Erasing one pattern does not modify other layers. |
| VER-06 | Undo/redo restores actual saved design state. |
| VER-07 | Unit switching does not alter physical measurements. |
| VER-08 | Unconfirmed template measurements remain identifiable. |
| VER-09 | Linked material changes update BOM references. |
| VER-10 | Embellishment counts match placements. |
| VER-11 | Export validation distinguishes required and optional information. |
| VER-12 | PDF pages readable, no clipped content. |
| VER-13 | Exported revisions unchanged after later edits. |
| VER-14 | Missing assets and failed exports produce actionable errors. |
| VER-15 | Unit tests for data transformations; integration/e2e tests for the core workflow. |

## CMP — Completion standard
| ID | Requirement |
|---|---|
| CMP-01 | Create a style. |
| CMP-02 | Choose any of the three garments. |
| CMP-03 | Edit individual panels. |
| CMP-04 | Add and manipulate artwork. |
| CMP-05 | Add patterns, textures, stitching, embellishments, hardware. |
| CMP-06 | Save and reopen without losing edits. |
| CMP-07 | View supported realistic ghost mockups. |
| CMP-08 | Enter measurements in cm or inches. |
| CMP-09 | Define colorways, materials, BOM, manufacturing notes. |
| CMP-10 | Export a readable, revisioned tech pack and supporting files. |
| CMP-11 | Clear local setup instructions and a demonstration project exercising the full workflow. |
