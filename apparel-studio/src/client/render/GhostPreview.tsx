import React, { useEffect, useRef, useState } from 'react';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { renderGhost, renderGhostPng } from './ghost';
import { Icon } from '../components/Icon';

export function GhostPreview() {
  const { doc, template } = useProject();
  const ui = useUi();
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<'idle' | 'rendering' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [renderedAt, setRenderedAt] = useState(0);

  useEffect(() => {
    if (!doc || !template?.ghost || !ref.current) return;
    let cancelled = false;
    const t = setTimeout(async () => {
      setState('rendering');
      const off = document.createElement('canvas');
      try {
        await renderGhost(off, { doc, template, view: ui.view, colorwayId: ui.colorwayId, scale: 1 });
        if (cancelled || !ref.current) return;
        ref.current.width = off.width;
        ref.current.height = off.height;
        ref.current.getContext('2d')!.drawImage(off, 0, 0);
        setState('idle');
        setError(null);
        setRenderedAt(Date.now());
      } catch (e) {
        if (!cancelled) {
          setState('error');
          setError((e as Error).message);
        }
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [doc, template, ui.view, ui.colorwayId]);

  if (!template) return null;
  if (!template.ghost) {
    return (
      <div className="canvas" style={{ display: 'grid', placeItems: 'center' }}>
        <div className="card" style={{ maxWidth: 460, padding: 18 }} data-testid="ghost-unavailable">
          <h3 style={{ marginBottom: 6 }}>No realistic preview for {template.name} yet</h3>
          <p className="hint">Ghost-mockup rendering assets (shading, highlight and displacement maps plus a calibrated mesh) are not installed for this garment. The technical view and tech pack are fully available. See TEMPLATE_AUTHORING.md for the asset specification.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="canvas" style={{ display: 'grid', placeItems: 'center', background: '#e9e9e6' }} data-testid="ghost-preview" data-rendered-at={renderedAt}>
      <canvas ref={ref} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} aria-label={`Realistic ${ui.view} mockup`} role="img" data-testid="ghost-canvas" />
      <div className="canvas-badge row">
        {state === 'rendering' && <span className="badge info">Rendering…</span>}
        <span className="badge" title={template.ghost.notes}>
          Appearance preview · {template.ghost.quality === 'procedural-v1' ? 'procedural shading assets' : 'photographic assets'}
        </span>
        <button
          className="btn sm"
          data-testid="download-mockup"
          onClick={async () => {
            if (!doc) return;
            try {
              const png = await renderGhostPng(doc, template, ui.view, ui.colorwayId, 3);
              const a = document.createElement('a');
              a.href = URL.createObjectURL(png);
              a.download = `${doc.styleNumber}_${ui.view}_mockup.png`;
              a.click();
              setTimeout(() => URL.revokeObjectURL(a.href), 2000);
            } catch (e) {
              ui.notify('error', `Mockup export failed: ${(e as Error).message}`);
            }
          }}
        >
          <Icon name="download" size={14} /> PNG (3×)
        </button>
      </div>
      {error && (
        <div className="canvas-hint" style={{ background: 'var(--err)' }} role="alert">
          {error}
        </div>
      )}
      <div className="canvas-hint" style={{ maxWidth: 560 }}>
        Appearance preview of colors, prints, embroidery, stones and hardware. It does not simulate fit or drape and is not a color standard or machine file.
      </div>
    </div>
  );
}
