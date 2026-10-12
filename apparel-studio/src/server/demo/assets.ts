/** Demo artwork authored for the sample project (original, no third-party marks). */
export const DEMO_LOGO_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
  <defs>
    <linearGradient id="sun" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffb347"/><stop offset="1" stop-color="#ff5e62"/>
    </linearGradient>
    <clipPath id="half"><rect x="0" y="0" width="400" height="190"/></clipPath>
  </defs>
  <g clip-path="url(#half)">
    <circle cx="200" cy="190" r="120" fill="url(#sun)"/>
    <rect x="70" y="130" width="260" height="10" fill="#1b1b2f"/>
    <rect x="70" y="152" width="260" height="13" fill="#1b1b2f"/>
    <rect x="70" y="176" width="260" height="16" fill="#1b1b2f"/>
  </g>
  <rect x="40" y="196" width="320" height="6" rx="3" fill="#1b1b2f"/>
  <text x="200" y="262" font-family="DejaVu Sans, Arial, sans-serif" font-weight="bold" font-size="52" letter-spacing="6" text-anchor="middle" fill="#1b1b2f">SUNSET</text>
  <text x="200" y="292" font-family="DejaVu Sans, Arial, sans-serif" font-size="22" letter-spacing="14" text-anchor="middle" fill="#1b1b2f">CLUB</text>
</svg>`;

export const DEMO_BACK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300">
  <circle cx="150" cy="150" r="138" fill="none" stroke="#1b1b2f" stroke-width="10"/>
  <circle cx="150" cy="150" r="112" fill="none" stroke="#ff5e62" stroke-width="4"/>
  <path d="M60,170 Q105,120 150,170 T240,170" fill="none" stroke="#1b1b2f" stroke-width="12" stroke-linecap="round"/>
  <path d="M60,200 Q105,150 150,200 T240,200" fill="none" stroke="#ffb347" stroke-width="12" stroke-linecap="round"/>
  <text x="150" y="112" font-family="DejaVu Sans, Arial, sans-serif" font-weight="bold" font-size="30" text-anchor="middle" fill="#1b1b2f">EST. 2026</text>
</svg>`;

export const DEMO_TILE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <rect width="120" height="120" fill="#f6efe3"/>
  <g fill="#ff8a5c" opacity="0.9">
    <circle cx="30" cy="30" r="12"/><circle cx="90" cy="90" r="12"/>
  </g>
  <g fill="#1b1b2f" opacity="0.85">
    <path d="M78,22 l6,10 l-12,0 z"/><path d="M18,82 l6,10 l-12,0 z"/>
  </g>
</svg>`;
