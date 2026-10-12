import { describe, expect, it } from 'vitest';
import { inspectPng, sanitizeSvg } from '../src/server/sanitize';
import { makePng } from './helpers';

describe('SVG sanitizer', () => {
  it('removes scripts, handlers, external refs and CSS imports', () => {
    const evil = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 50" onload="alert(1)">
      <style>@import url(http://evil/x.css); .a{fill:url(http://evil/p.svg#x)}</style>
      <script>alert(1)</script><a href="javascript:alert(1)"><rect width="1" height="1"/></a>
      <image href="https://evil/t.png" width="5" height="5"/><use xlink:href="http://evil/s.svg#a"/>
      <foreignObject><div>x</div></foreignObject><rect onclick="x()" style="fill:url(http://x)" width="20" height="20"/></svg>`;
    const r = sanitizeSvg(Buffer.from(evil));
    expect(r.svg.replace(/xmlns(:xlink)?="[^"]*"/g, '')).not.toMatch(/script|onload|onclick|javascript:|http:|https:|@import|foreignObject/i);
    expect(r.width).toBe(100);
    expect(r.height).toBe(50);
    expect(r.removed).toBeGreaterThan(0);
  });

  it('keeps safe internal references and gradients', () => {
    const ok = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs><rect width="10" height="10" fill="url(#g)"/></svg>`;
    expect(sanitizeSvg(Buffer.from(ok)).svg).toContain('url(#g)');
    // A clean file reports nothing removed (no false "unsafe content" warning).
    expect(sanitizeSvg(Buffer.from(ok)).removed).toBe(0);
  });

  it('rejects DTDs and files without dimensions', () => {
    expect(() => sanitizeSvg(Buffer.from('<!DOCTYPE svg [<!ENTITY x "y">]><svg viewBox="0 0 1 1"/>'))).toThrow(/DOCTYPE/);
    expect(() => sanitizeSvg(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'))).toThrow(/viewBox/);
    expect(() => sanitizeSvg(Buffer.from('hello'))).toThrow();
  });
});

describe('PNG inspection', () => {
  it('reads dimensions and alpha', () => {
    expect(inspectPng(makePng(40, 20))).toEqual({ width: 40, height: 20, hasAlpha: true });
    expect(inspectPng(makePng(8, 8, false)).hasAlpha).toBe(false);
    expect(() => inspectPng(Buffer.from('not a png at all, definitely not'))).toThrow(/PNG/);
  });
});
