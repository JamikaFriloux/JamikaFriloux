import type { StitchStyle } from '../schema/template';

/**
 * Illustrative stitch appearance. These dashes are a visual convention only; they do not
 * specify stitch type, SPI, or seam construction (that belongs in manufacturing notes).
 */
export const STITCH_DASH: Record<StitchStyle, { dash: string; width: number; rows: 1 | 2 }> = {
  'single-needle': { dash: '6 4', width: 1.6, rows: 1 },
  'double-needle': { dash: '6 4', width: 1.6, rows: 2 },
  coverstitch: { dash: '5 3', width: 1.8, rows: 2 },
  overlock: { dash: '2 2', width: 2.4, rows: 1 },
  'topstitch-contrast': { dash: '8 4', width: 2.4, rows: 1 },
  zigzag: { dash: '3 3', width: 3, rows: 1 },
  bartack: { dash: '1 1', width: 4, rows: 1 },
};
