/**
 * Physical units. Canonical storage unit is the millimetre, quantised to 1/10 000 mm
 * (stored as a plain number with at most 4 decimals). Every conversion goes through
 * integer arithmetic on scaled values, so inch fractions such as 1/16" (1.5875 mm) are
 * exact, and switching the *display* unit never rewrites stored values.
 */

export type LengthUnit = 'mm' | 'cm' | 'in';

/** 1 mm expressed in canonical quanta. */
const Q = 10000n;
/** 1 inch = 25.4 mm exactly = 254000 quanta. */
const INCH_Q = 254000n;
const CM_Q = 100000n;

export function unitQuanta(unit: LengthUnit): bigint {
  return unit === 'mm' ? Q : unit === 'cm' ? CM_Q : INCH_Q;
}

/** Round a millimetre number to the canonical 4-decimal grid. */
export function roundMm(mm: number): number {
  return Math.round(mm * 10000) / 10000;
}

function mmToQuanta(mm: number): bigint {
  return BigInt(Math.round(mm * 10000));
}

function quantaToMm(q: bigint): number {
  return Number(q) / 10000;
}

/** Divide with half-away-from-zero rounding. */
function divRound(a: bigint, b: bigint): bigint {
  const neg = a < 0n !== b < 0n;
  const aa = a < 0n ? -a : a;
  const bb = b < 0n ? -b : b;
  const q = (aa * 2n + bb) / (2n * bb);
  return neg ? -q : q;
}

/**
 * Parse user text into an exact rational (numerator/denominator), supporting
 * decimals ("12.375"), fractions ("3/8"), and mixed numbers ("12 3/8", "12-3/8").
 * Returns null for unparseable input.
 */
export function parseRational(text: string): { num: bigint; den: bigint } | null {
  const s = text.trim().replace(/["”]|in$|cm$|mm$/g, '').trim();
  if (!s) return null;
  const mixed = /^(-)?(\d+)[\s-]+(\d+)\/(\d+)$/.exec(s);
  if (mixed) {
    const sign = mixed[1] ? -1n : 1n;
    const den = BigInt(mixed[4]);
    if (den === 0n) return null;
    return { num: sign * (BigInt(mixed[2]) * den + BigInt(mixed[3])), den };
  }
  const frac = /^(-)?(\d+)\/(\d+)$/.exec(s);
  if (frac) {
    const den = BigInt(frac[3]);
    if (den === 0n) return null;
    return { num: (frac[1] ? -1n : 1n) * BigInt(frac[2]), den };
  }
  const dec = /^(-)?(\d*)(?:\.(\d+))?$/.exec(s);
  if (dec && (dec[2] || dec[3])) {
    const intPart = dec[2] || '0';
    const fracPart = dec[3] || '';
    const den = 10n ** BigInt(fracPart.length);
    const num = BigInt(intPart + fracPart);
    return { num: (dec[1] ? -1n : 1n) * num, den };
  }
  return null;
}

/** Parse a length typed in `unit` into canonical millimetres. Null if invalid. */
export function parseLength(text: string, unit: LengthUnit): number | null {
  const r = parseRational(text);
  if (!r) return null;
  const q = divRound(r.num * unitQuanta(unit), r.den);
  return quantaToMm(q);
}

/** Convert canonical mm to a number in the display unit (rounded for display only). */
export function mmToUnit(mm: number, unit: LengthUnit, decimals?: number): number {
  const d = decimals ?? defaultDecimals(unit);
  const q = mmToQuanta(mm);
  const scale = 10n ** BigInt(d);
  const v = divRound(q * scale, unitQuanta(unit));
  return Number(v) / Number(scale);
}

export function defaultDecimals(unit: LengthUnit): number {
  return unit === 'mm' ? 1 : unit === 'cm' ? 2 : 3;
}

/** Display string such as "29.5 cm" or "11 5/8 in". Pure presentation. */
export function formatLength(
  mm: number | null | undefined,
  unit: LengthUnit,
  opts: { fractions?: boolean; withUnit?: boolean } = {},
): string {
  if (mm === null || mm === undefined || Number.isNaN(mm)) return '';
  const withUnit = opts.withUnit ?? true;
  let body: string;
  if (unit === 'in' && opts.fractions) {
    body = toInchFraction(mm);
  } else {
    body = trimZeros(mmToUnit(mm, unit).toFixed(defaultDecimals(unit)));
  }
  return withUnit ? `${body} ${unit}` : body;
}

function trimZeros(s: string): string {
  return s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s;
}

/** Nearest 1/16" representation; falls back to decimals if not within 0.01 mm of a 1/16. */
export function toInchFraction(mm: number): string {
  const q = mmToQuanta(mm);
  const sixteenths = divRound(q * 16n, INCH_Q);
  const back = divRound(sixteenths * INCH_Q, 16n);
  const diff = back > q ? back - q : q - back;
  if (diff > 100n) return trimZeros(mmToUnit(mm, 'in').toFixed(3));
  const neg = sixteenths < 0n;
  let n = neg ? -sixteenths : sixteenths;
  const whole = n / 16n;
  let rem = n % 16n;
  let den = 16n;
  while (rem !== 0n && rem % 2n === 0n) {
    rem /= 2n;
    den /= 2n;
  }
  n = whole;
  const sign = neg ? '-' : '';
  if (rem === 0n) return `${sign}${whole}`;
  return whole === 0n ? `${sign}${rem}/${den}` : `${sign}${whole} ${rem}/${den}`;
}

export function convertWeight(value: number, from: 'gsm' | 'oz/yd2', to: 'gsm' | 'oz/yd2'): number {
  if (from === to) return value;
  // 1 oz/yd² = 33.906 g/m² (by definition of the ounce and yard).
  const factor = 33.9057475;
  return from === 'oz/yd2' ? value * factor : value / factor;
}
