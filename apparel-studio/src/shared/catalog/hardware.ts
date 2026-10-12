/**
 * Curated hardware / trim components. Placing hardware is a *visual placement* plus a BOM
 * link; it never changes the garment template's structure (e.g. a decorative zipper on a
 * pullover does not make it a zip hoodie).
 */
export interface HardwareDef {
  id: string;
  name: string;
  category: 'eyelet' | 'aglet' | 'stopper' | 'snap' | 'rivet' | 'zipper-decorative' | 'ring' | 'badge' | 'toggle';
  defaultSizeMm: number;
  /** Aspect ratio width/height of the drawing. */
  aspect: number;
  finishes: string[];
  /** Symbol drawn in a 100 x (100/aspect) box. Uses currentColor for the metal tone. */
  svg: string;
  /** Explains the structural implication (or lack of one). */
  structuralNote: string;
}

export const HARDWARE: HardwareDef[] = [
  {
    id: 'eyelet',
    name: 'Metal eyelet / grommet',
    category: 'eyelet',
    defaultSizeMm: 10,
    aspect: 1,
    finishes: ['Nickel', 'Matte black', 'Antique brass', 'Gunmetal', 'Gold'],
    svg: '<circle cx="50" cy="50" r="46" fill="currentColor"/><circle cx="50" cy="50" r="30" fill="#000" fill-opacity="0.55"/><circle cx="50" cy="50" r="40" fill="none" stroke="#fff" stroke-opacity="0.35" stroke-width="4"/>',
    structuralNote: 'Visual placement. Eyelets imply a punched hole: confirm in construction notes if functional.',
  },
  {
    id: 'aglet-metal',
    name: 'Metal drawcord tip (aglet)',
    category: 'aglet',
    defaultSizeMm: 25,
    aspect: 0.32,
    finishes: ['Nickel', 'Matte black', 'Antique brass', 'Gold'],
    svg: '<rect x="4" y="2" width="24" height="300" rx="10" fill="currentColor"/><rect x="8" y="10" width="6" height="280" rx="3" fill="#fff" fill-opacity="0.35"/>',
    structuralNote: 'Visual placement of a trim on an existing drawcord.',
  },
  {
    id: 'cord-stopper',
    name: 'Cord stopper',
    category: 'stopper',
    defaultSizeMm: 18,
    aspect: 0.75,
    finishes: ['Matte black plastic', 'Nickel', 'Gunmetal'],
    svg: '<rect x="4" y="4" width="67" height="125" rx="20" fill="currentColor"/><circle cx="37" cy="66" r="12" fill="#000" fill-opacity="0.6"/>',
    structuralNote: 'Visual placement only.',
  },
  {
    id: 'snap',
    name: 'Snap button',
    category: 'snap',
    defaultSizeMm: 12,
    aspect: 1,
    finishes: ['Nickel', 'Matte black', 'Antique brass'],
    svg: '<circle cx="50" cy="50" r="46" fill="currentColor"/><circle cx="50" cy="50" r="22" fill="#fff" fill-opacity="0.3"/><circle cx="50" cy="50" r="8" fill="#000" fill-opacity="0.4"/>',
    structuralNote: 'Visual placement. A functional snap requires a construction change that this template does not define.',
  },
  {
    id: 'rivet',
    name: 'Rivet',
    category: 'rivet',
    defaultSizeMm: 8,
    aspect: 1,
    finishes: ['Copper', 'Nickel', 'Antique brass'],
    svg: '<circle cx="50" cy="50" r="46" fill="currentColor"/><circle cx="42" cy="42" r="16" fill="#fff" fill-opacity="0.4"/>',
    structuralNote: 'Visual placement only.',
  },
  {
    id: 'zipper-decorative',
    name: 'Decorative zipper (non-functional)',
    category: 'zipper-decorative',
    defaultSizeMm: 160,
    aspect: 0.16,
    finishes: ['Nickel teeth', 'Matte black teeth', 'Gold teeth'],
    svg: '<rect x="0" y="0" width="100" height="625" rx="6" fill="#222" fill-opacity="0.85"/><g fill="currentColor">' +
      Array.from({ length: 30 }, (_, i) => `<rect x="${i % 2 ? 50 : 22}" y="${10 + i * 20}" width="28" height="12" rx="3"/>`).join('') +
      '</g><rect x="28" y="590" width="44" height="30" rx="6" fill="currentColor"/>',
    structuralNote: 'Decorative only. The garment stays a pullover; no opening or zipper construction is specified.',
  },
  {
    id: 'd-ring',
    name: 'D-ring',
    category: 'ring',
    defaultSizeMm: 25,
    aspect: 1,
    finishes: ['Nickel', 'Matte black', 'Gunmetal'],
    svg: '<path d="M20,10 L50,10 A40,40 0 0 1 50,90 L20,90 Z" fill="none" stroke="currentColor" stroke-width="12"/>',
    structuralNote: 'Visual placement. Attachment tab must be described in construction notes.',
  },
  {
    id: 'metal-badge',
    name: 'Metal badge plate',
    category: 'badge',
    defaultSizeMm: 40,
    aspect: 2.5,
    finishes: ['Brushed silver', 'Matte black', 'Gold', 'Gunmetal'],
    svg: '<rect x="2" y="2" width="246" height="96" rx="12" fill="currentColor"/><rect x="12" y="12" width="226" height="76" rx="8" fill="none" stroke="#fff" stroke-opacity="0.35" stroke-width="4"/>',
    structuralNote: 'Visual placement only.',
  },
];

export function getHardware(id: string): HardwareDef | undefined {
  return HARDWARE.find((h) => h.id === id);
}

export const FINISH_COLORS: Record<string, string> = {
  Nickel: '#c9ccd1',
  'Matte black': '#2a2a2c',
  'Matte black plastic': '#232325',
  'Antique brass': '#9a7b45',
  Gunmetal: '#5a5d63',
  Gold: '#d4af37',
  Copper: '#b87333',
  'Brushed silver': '#b9bcc2',
  'Nickel teeth': '#c9ccd1',
  'Matte black teeth': '#2a2a2c',
  'Gold teeth': '#d4af37',
};
