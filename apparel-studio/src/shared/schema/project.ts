import { z } from 'zod';
import { decorationMethodSchema, stitchStyleSchema } from './template';

const id = z.string().min(1).max(64);
const hex = z.string().regex(/^#[0-9a-fA-F]{6}$/);
const opacity = z.number().min(0).max(1);
const mm = z.number().finite();

/* ------------------------------------------------------------------ */
/* Palette, materials, colorways                                        */
/* ------------------------------------------------------------------ */

export const colorSchema = z.object({
  id,
  name: z.string().min(1).max(80),
  /** Screen display value only. Does not guarantee physical fabric colour. */
  hex,
  /** User-supplied colour-standard reference. Never auto-generated. */
  standard: z
    .object({ system: z.string().max(40), code: z.string().max(40) })
    .nullable()
    .default(null),
  approval: z.enum(['not-submitted', 'submitted', 'approved', 'rejected']).default('not-submitted'),
});
export type Color = z.infer<typeof colorSchema>;

export const materialSchema = z.object({
  id,
  name: z.string().min(1).max(120),
  kind: z.enum(['fabric', 'rib', 'trim', 'thread', 'label', 'packaging', 'other']),
  composition: z.string().max(200).default(''),
  weight: z
    .object({ value: z.number().positive(), unit: z.enum(['gsm', 'oz/yd2']) })
    .nullable()
    .default(null),
  finish: z.string().max(200).default(''),
  supplier: z.string().max(120).default(''),
  supplierRef: z.string().max(120).default(''),
  /** Curated texture used for the appearance preview of this material. */
  textureId: z.string().nullable().default(null),
  notes: z.string().max(2000).default(''),
});
export type Material = z.infer<typeof materialSchema>;

export const colorwaySchema = z.object({
  id,
  name: z.string().min(1).max(80),
  code: z.string().max(40).default(''),
  /** Explicit substitutions relative to the base design: base colour id → colour id. */
  colorSubs: z.record(z.string(), z.string()).default({}),
  /** base material id → material id. */
  materialSubs: z.record(z.string(), z.string()).default({}),
  notes: z.string().max(1000).default(''),
});
export type Colorway = z.infer<typeof colorwaySchema>;

/* ------------------------------------------------------------------ */
/* Layers                                                               */
/* ------------------------------------------------------------------ */

export const transformSchema = z.object({
  /** Centre position in template view units. */
  x: z.number(),
  y: z.number(),
  width: z.number().positive(),
  height: z.number().positive(),
  /** Degrees clockwise. */
  rotation: z.number(),
});
export type Transform = z.infer<typeof transformSchema>;

export const maskStrokeSchema = z.object({
  mode: z.enum(['erase', 'restore']),
  /** Strokes are in the coordinates of the view they were painted in. */
  view: z.enum(['front', 'back']),
  /** Brush diameter in view units. */
  width: z.number().positive(),
  /** Flat list x0,y0,x1,y1,... in view units. */
  points: z.array(z.number()).min(2),
});
export type MaskStroke = z.infer<typeof maskStrokeSchema>;

export const layerViewSchema = z.enum(['front', 'back', 'all']);

const layerBase = {
  id,
  name: z.string().min(1).max(120),
  /** `all` = applies to every view where its target components appear. */
  view: layerViewSchema,
  /** Component ids this layer targets (and clips to, where applicable). */
  targets: z.array(z.string()),
  visible: z.boolean().default(true),
  locked: z.boolean().default(false),
  opacity: opacity.default(1),
  /** Optional link to a manual BOM row. */
  bomItemId: z.string().nullable().default(null),
};

export const panelFillLayerSchema = z.object({
  ...layerBase,
  type: z.literal('panelFill'),
  colorId: z.string(),
  materialId: z.string().nullable(),
});

export const placementSchema = z.object({
  anchorId: z.string().nullable(),
  /** Which point of the artwork the offsets measure to. */
  reference: z.enum(['center', 'top-center']),
  offsetXmm: mm,
  offsetYmm: mm,
  widthMm: mm.positive(),
  heightMm: mm.positive(),
  toleranceMm: mm.nonnegative().nullable(),
  /**
   * `canvas-estimate`: derived from the nominal drawing scale (visual only).
   * `entered`: explicit manufacturing dimensions typed by the user.
   */
  source: z.enum(['canvas-estimate', 'entered']),
});
export type Placement = z.infer<typeof placementSchema>;

export const artworkLayerSchema = z.object({
  ...layerBase,
  type: z.literal('artwork'),
  assetId: z.string(),
  transform: transformSchema,
  lockAspect: z.boolean().default(true),
  /** When true, the artwork is clipped to the union of `targets` panels in the view. */
  clipToTargets: z.boolean().default(true),
  mask: z.array(maskStrokeSchema).default([]),
  placement: placementSchema,
  decoration: z.object({
    method: decorationMethodSchema,
    artworkCode: z.string().max(60).default(''),
    colorIds: z.array(z.string()).default([]),
    notes: z.string().max(2000).default(''),
  }),
});

export const patternLayerSchema = z.object({
  ...layerBase,
  type: z.literal('pattern'),
  assetId: z.string(),
  /** Physical repeat width of one tile in mm (height follows tile aspect). */
  tileWidthMm: mm.positive(),
  rotation: z.number(),
  offsetXmm: mm,
  offsetYmm: mm,
  mask: z.array(maskStrokeSchema).default([]),
  method: decorationMethodSchema.default('sublimation'),
  notes: z.string().max(2000).default(''),
});

export const textureLayerSchema = z.object({
  ...layerBase,
  type: z.literal('texture'),
  textureId: z.string(),
  /** Appearance scale multiplier. */
  scale: z.number().min(0.1).max(10),
  /** 0..1 strength of the surface effect. */
  strength: z.number().min(0).max(1),
  /** Material this texture represents (links the preview to the specification). */
  materialId: z.string().nullable(),
  mask: z.array(maskStrokeSchema).default([]),
});

export const stitchingLayerSchema = z.object({
  ...layerBase,
  type: z.literal('stitching'),
  seamIds: z.array(z.string()).min(1),
  colorId: z.string(),
  style: stitchStyleSchema,
  /** Manufacturing notes; the drawn dash is illustrative only. */
  notes: z.string().max(2000).default(''),
  threadMaterialId: z.string().nullable().default(null),
});

export const pointSchema = z.object({ x: z.number(), y: z.number() });

export const embellishmentPathSchema = z.object({
  id,
  points: z.array(pointSchema).min(2),
  spacingMm: mm.positive(),
});

export const embellishmentLayerSchema = z.object({
  ...layerBase,
  type: z.literal('embellishment'),
  kind: z.enum(['rhinestone', 'stud']),
  points: z.array(pointSchema).default([]),
  paths: z.array(embellishmentPathSchema).default([]),
  diameterMm: mm.positive(),
  finish: z.string().max(60),
  colorId: z.string().nullable().default(null),
  attachment: z.enum(['hotfix', 'prong-set', 'sew-on', 'glue-on']),
  notes: z.string().max(2000).default(''),
});

export const hardwareLayerSchema = z.object({
  ...layerBase,
  type: z.literal('hardware'),
  hardwareId: z.string(),
  transform: transformSchema,
  finish: z.string().max(60),
  sizeMm: mm.positive(),
  notes: z.string().max(2000).default(''),
});

export const annotationLayerSchema = z.object({
  ...layerBase,
  type: z.literal('annotation'),
  text: z.string().min(1).max(500),
  /** Text position. */
  x: z.number(),
  y: z.number(),
  /** Optional leader target. */
  target: pointSchema.nullable().default(null),
});

export const layerSchema = z.discriminatedUnion('type', [
  panelFillLayerSchema,
  artworkLayerSchema,
  patternLayerSchema,
  textureLayerSchema,
  stitchingLayerSchema,
  embellishmentLayerSchema,
  hardwareLayerSchema,
  annotationLayerSchema,
]);

export type Layer = z.infer<typeof layerSchema>;
export type LayerType = Layer['type'];
export type PanelFillLayer = z.infer<typeof panelFillLayerSchema>;
export type ArtworkLayer = z.infer<typeof artworkLayerSchema>;
export type PatternLayer = z.infer<typeof patternLayerSchema>;
export type TextureLayer = z.infer<typeof textureLayerSchema>;
export type StitchingLayer = z.infer<typeof stitchingLayerSchema>;
export type EmbellishmentLayer = z.infer<typeof embellishmentLayerSchema>;
export type HardwareLayer = z.infer<typeof hardwareLayerSchema>;
export type AnnotationLayer = z.infer<typeof annotationLayerSchema>;
export type Point = z.infer<typeof pointSchema>;

/* ------------------------------------------------------------------ */
/* Assets, measurements, BOM, notes                                     */
/* ------------------------------------------------------------------ */

export const assetRefSchema = z.object({
  id,
  kind: z.enum(['png', 'svg']),
  role: z.enum(['artwork', 'pattern-tile', 'label', 'reference']),
  filename: z.string().max(200),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  width: z.number().positive(),
  height: z.number().positive(),
  bytes: z.number().int().nonnegative(),
});
export type AssetRef = z.infer<typeof assetRefSchema>;

export const measurementValueSchema = z.object({
  mm: mm.nullable(),
  source: z.enum(['template-default', 'entered']),
});

export const pomSchema = z.object({
  id,
  /** Template POM this row came from; null for custom POMs. */
  templatePomId: z.string().nullable(),
  code: z.string().min(1).max(12),
  label: z.string().min(1).max(120),
  howToMeasure: z.string().max(1000),
  diagramView: z.enum(['front', 'back']),
  values: z.record(z.string(), measurementValueSchema),
  tolPlusMm: mm.nonnegative(),
  tolMinusMm: mm.nonnegative(),
  /** Where the values came from (free text, e.g. "Template default", "Factory sample 1"). */
  source: z.string().max(120),
  confirmed: z.boolean(),
});
export type Pom = z.infer<typeof pomSchema>;

export const bomCategorySchema = z.enum(['fabric', 'trim', 'thread', 'label', 'packaging', 'embellishment', 'hardware', 'other']);
export const quantityTypeSchema = z.enum(['counted', 'entered', 'estimated']);

export const bomItemSchema = z.object({
  id,
  category: bomCategorySchema,
  component: z.string().max(120),
  materialId: z.string().nullable(),
  description: z.string().max(300),
  quantity: z.number().nonnegative().nullable(),
  unit: z.string().max(20),
  /** Manual rows are never `counted`. */
  quantityType: z.enum(['entered', 'estimated']),
  /** Empty = all colorways. */
  colorwayIds: z.array(z.string()).default([]),
  supplierRef: z.string().max(120).default(''),
  notes: z.string().max(1000).default(''),
});
export type BomItem = z.infer<typeof bomItemSchema>;

/** User inputs attached to an automatically derived BOM row, keyed by the row's derived key. */
export const bomDerivedInputSchema = z.object({
  quantity: z.number().nonnegative().nullable().default(null),
  unit: z.string().max(20).default(''),
  quantityType: z.enum(['entered', 'estimated']).default('entered'),
  supplierRef: z.string().max(120).default(''),
  notes: z.string().max(1000).default(''),
});
export type BomDerivedInput = z.infer<typeof bomDerivedInputSchema>;

export const constructionNoteSchema = z.object({
  id,
  title: z.string().min(1).max(120),
  text: z.string().max(4000),
  componentIds: z.array(z.string()).default([]),
  seamIds: z.array(z.string()).default([]),
});
export type ConstructionNote = z.infer<typeof constructionNoteSchema>;

export const labelItemSchema = z.object({
  id,
  type: z.enum(['main-label', 'size-label', 'care-label', 'hang-tag', 'heat-transfer-label', 'polybag', 'folding', 'carton', 'other']),
  description: z.string().max(500),
  placement: z.string().max(300).default(''),
  materialId: z.string().nullable().default(null),
  assetId: z.string().nullable().default(null),
  notes: z.string().max(1000).default(''),
});
export type LabelItem = z.infer<typeof labelItemSchema>;

/* ------------------------------------------------------------------ */
/* Project document                                                     */
/* ------------------------------------------------------------------ */

export const PROJECT_SCHEMA_VERSION = 1;

export const projectDocSchema = z.object({
  schemaVersion: z.literal(PROJECT_SCHEMA_VERSION),
  name: z.string().min(1).max(120),
  styleNumber: z.string().min(1).max(40),
  season: z.string().max(40).default(''),
  /** Collection / set name used to group styles (each keeps its own spec). */
  collection: z.string().max(80).default(''),
  description: z.string().max(2000).default(''),
  template: z.object({ id: z.string(), version: z.number().int().positive() }),
  sizes: z.object({ base: z.string(), range: z.array(z.string()).min(1) }),
  displayUnit: z.enum(['cm', 'in']),
  colors: z.array(colorSchema),
  materials: z.array(materialSchema),
  colorways: z.array(colorwaySchema).min(1),
  /** Array order is stacking order (index 0 draws first). */
  layers: z.array(layerSchema),
  assets: z.array(assetRefSchema),
  measurements: z.array(pomSchema),
  bomItems: z.array(bomItemSchema),
  bomDerived: z.record(z.string(), bomDerivedInputSchema).default({}),
  constructionNotes: z.array(constructionNoteSchema),
  labels: z.array(labelItemSchema),
});
export type ProjectDoc = z.infer<typeof projectDocSchema>;

/** Project as served by the API (document + relational metadata). */
export interface ProjectRecord {
  id: string;
  doc: ProjectDoc;
  version: number;
  createdAt: string;
  updatedAt: string;
  archived: boolean;
}

export interface ProjectSummary {
  id: string;
  name: string;
  styleNumber: string;
  collection: string;
  templateId: string;
  templateVersion: number;
  updatedAt: string;
  archived: boolean;
  revisionCount: number;
}

export interface RevisionSummary {
  id: string;
  projectId: string;
  number: number;
  label: string;
  kind: 'draft' | 'review';
  notes: string;
  createdAt: string;
  snapshotHash: string;
  exports: ExportSummary[];
}

export interface ExportSummary {
  id: string;
  kind: 'pdf' | 'bom-csv' | 'measurements-csv' | 'mockup-png';
  filename: string;
  status: 'ok' | 'failed';
  error: string | null;
  createdAt: string;
}
