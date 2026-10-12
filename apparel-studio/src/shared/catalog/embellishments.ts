/** Common rhinestone and stud presets. Sizes are standard nominal diameters. */
export const RHINESTONE_SIZES = [
  { label: 'SS6', diameterMm: 2.0 },
  { label: 'SS10', diameterMm: 2.8 },
  { label: 'SS16', diameterMm: 3.9 },
  { label: 'SS20', diameterMm: 4.7 },
  { label: 'SS30', diameterMm: 6.4 },
];
export const STUD_SIZES = [
  { label: '4 mm', diameterMm: 4 },
  { label: '6 mm', diameterMm: 6 },
  { label: '8 mm', diameterMm: 8 },
  { label: '10 mm', diameterMm: 10 },
];
export const RHINESTONE_FINISHES = ['Crystal', 'Crystal AB', 'Jet', 'Rose', 'Sapphire', 'Emerald', 'Light Gold'];
export const STUD_FINISHES = ['Nickel', 'Matte black', 'Gold', 'Gunmetal', 'Antique brass'];

export const EMBELLISHMENT_FINISH_COLORS: Record<string, string> = {
  Crystal: '#e9eef5',
  'Crystal AB': '#dfe9f7',
  Jet: '#1b1b1f',
  Rose: '#f2a7b8',
  Sapphire: '#2f55c9',
  Emerald: '#1f9a62',
  'Light Gold': '#e8cf86',
  Nickel: '#c9ccd1',
  'Matte black': '#2a2a2c',
  Gold: '#d4af37',
  Gunmetal: '#5a5d63',
  'Antique brass': '#9a7b45',
};

export function sizeLabelFor(kind: 'rhinestone' | 'stud', diameterMm: number): string {
  const list = kind === 'rhinestone' ? RHINESTONE_SIZES : STUD_SIZES;
  const hit = list.find((s) => Math.abs(s.diameterMm - diameterMm) < 0.05);
  return hit ? hit.label : `${diameterMm} mm`;
}
