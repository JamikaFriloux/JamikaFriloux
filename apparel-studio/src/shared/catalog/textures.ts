/**
 * Curated texture library. Textures are *appearance* previews generated procedurally and
 * deterministically (no bitmaps required). Linking a texture to a material record is what
 * ties the preview to the actual specification.
 */
export type TextureKind = 'jersey' | 'rib' | 'pique' | 'waffle' | 'fleece' | 'terry' | 'slub' | 'twill';

export interface TextureDef {
  id: string;
  name: string;
  kind: TextureKind;
  description: string;
  /** Repeat size of one procedural tile in mm at scale 1. */
  tileMm: number;
}

export const TEXTURES: TextureDef[] = [
  { id: 'jersey', name: 'Single jersey', kind: 'jersey', description: 'Fine knit face typical of T-shirts.', tileMm: 6 },
  { id: 'jersey-heavy', name: 'Heavyweight jersey', kind: 'jersey', description: 'Denser, more visible knit loops.', tileMm: 9 },
  { id: 'slub', name: 'Slub jersey', kind: 'slub', description: 'Irregular yarn thickness streaks.', tileMm: 40 },
  { id: 'rib-1x1', name: '1x1 rib', kind: 'rib', description: 'Fine vertical ribs for necklines and cuffs.', tileMm: 2.4 },
  { id: 'rib-2x2', name: '2x2 rib', kind: 'rib', description: 'Wider vertical ribs for cuffs and waistbands.', tileMm: 4.8 },
  { id: 'pique', name: 'Piqué', kind: 'pique', description: 'Small honeycomb texture.', tileMm: 4 },
  { id: 'waffle', name: 'Waffle / thermal', kind: 'waffle', description: 'Square cell grid.', tileMm: 8 },
  { id: 'fleece', name: 'Fleece face', kind: 'fleece', description: 'Soft, low-contrast surface for hoodies and sweatpants.', tileMm: 30 },
  { id: 'terry', name: 'French terry face', kind: 'terry', description: 'Smooth face with faint loop structure.', tileMm: 12 },
  { id: 'twill-tape', name: 'Twill', kind: 'twill', description: 'Diagonal twill lines for tapes and woven trims.', tileMm: 3 },
];

export function getTexture(id: string): TextureDef | undefined {
  return TEXTURES.find((t) => t.id === id);
}
