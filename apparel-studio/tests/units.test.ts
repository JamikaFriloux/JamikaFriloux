import { describe, expect, it } from 'vitest';
import { formatLength, mmToUnit, parseLength, parseRational, toInchFraction } from '../src/shared/units';

describe('units', () => {
  it('parses decimals, fractions and mixed numbers exactly', () => {
    expect(parseRational('12.375')).toEqual({ num: 12375n, den: 1000n });
    expect(parseLength('1/16', 'in')).toBe(1.5875);
    expect(parseLength('12 3/8', 'in')).toBe(314.325);
    expect(parseLength('12-3/8"', 'in')).toBe(314.325);
    expect(parseLength('59.2', 'cm')).toBe(592);
    expect(parseLength('abc', 'cm')).toBeNull();
    expect(parseLength('1/0', 'in')).toBeNull();
  });

  it('display unit switching never changes the stored value', () => {
    const stored = 592;
    const asCm = formatLength(stored, 'cm');
    const asIn = formatLength(stored, 'in');
    expect(asCm).toBe('59.2 cm');
    expect(asIn).toBe('23.307 in');
    // Formatting is pure: stored canonical value is untouched.
    expect(stored).toBe(592);
  });

  it('round trips inch entry without cumulative drift', () => {
    let mm = parseLength('23 5/16', 'in')!;
    for (let i = 0; i < 50; i++) {
      // Re-enter what is displayed, alternating units, 50 times.
      const shownIn = toInchFraction(mm);
      mm = parseLength(shownIn, 'in')!;
      const shownCm = mmToUnit(mm, 'cm', 5).toString(); // canonical grid is exact at 5 cm decimals
      mm = parseLength(shownCm, 'cm')!;
    }
    expect(mm).toBe(parseLength('23 5/16', 'in'));
    expect(toInchFraction(mm)).toBe('23 5/16');
  });

  it('formats inch fractions and falls back to decimals', () => {
    expect(toInchFraction(25.4)).toBe('1');
    expect(toInchFraction(12.7)).toBe('1/2');
    expect(toInchFraction(10)).toBe('0.394');
    expect(formatLength(null, 'cm')).toBe('');
  });
});
