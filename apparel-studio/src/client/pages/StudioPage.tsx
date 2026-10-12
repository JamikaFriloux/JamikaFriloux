import React from 'react';
import { EditorCanvas } from '../components/EditorCanvas';
import { LeftPanel } from '../components/LeftPanel';
import { Inspector } from '../components/Inspector';
import { GhostPreview } from '../render/GhostPreview';
import { useProject } from '../store/project';
import { useUi } from '../store/ui';
import { Icon } from '../components/Icon';

export function StudioPage() {
  const { doc, template } = useProject();
  const ui = useUi();
  if (!doc || !template) return null;
  const hasGhost = !!template.ghost;
  return (
    <div className="studio">
      <LeftPanel />
      <section className="canvas-wrap" aria-label="Design canvas">
        <div className="canvas-toolbar">
          <div className="seg" role="group" aria-label="View">
            {template.views.map((v) => (
              <button key={v.id} aria-pressed={ui.view === v.id} onClick={() => ui.set({ view: v.id, tool: { kind: 'select' } })} data-testid={`view-${v.id}`}>
                {v.label}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Preview">
            <button aria-pressed={ui.preview === 'technical'} onClick={() => ui.set({ preview: 'technical' })} data-testid="preview-technical">
              Technical
            </button>
            <button aria-pressed={ui.preview === 'realistic'} onClick={() => ui.set({ preview: 'realistic', tool: { kind: 'select' } })} data-testid="preview-realistic" title={hasGhost ? 'Ghost mockup preview' : 'No ghost rendering assets for this garment'}>
              Realistic
            </button>
          </div>
          {doc.colorways.length > 1 && (
            <select className="input sm" style={{ width: 160 }} value={ui.colorwayId ?? ''} onChange={(e) => ui.set({ colorwayId: e.target.value })} aria-label="Colorway">
              {doc.colorways.map((c) => (
                <option key={c.id} value={c.id}>
                  Colorway: {c.name}
                </option>
              ))}
            </select>
          )}
          <div className="spacer" />
          {ui.preview === 'technical' && (
            <>
              <button className={`btn sm icon${ui.tool.kind === 'select' ? ' active' : ''}`} aria-label="Select tool" title="Select (Esc)" onClick={() => ui.set({ tool: { kind: 'select' } })}>
                <Icon name="pointer" size={15} />
              </button>
              <button className={`btn sm icon${ui.tool.kind === 'pan' ? ' active' : ''}`} aria-label="Pan tool" title="Pan (or hold Space)" onClick={() => ui.set({ tool: { kind: 'pan' } })}>
                <Icon name="hand" size={15} />
              </button>
              <button className="btn sm icon" aria-label="Zoom out" onClick={() => ui.set({ zoom: Math.max(0.4, ui.zoom / 1.25) })}>
                <Icon name="zoomOut" size={15} />
              </button>
              <span className="small mono" style={{ width: 42, textAlign: 'center' }} aria-label="Zoom level">
                {Math.round(ui.zoom * 100)}%
              </span>
              <button className="btn sm icon" aria-label="Zoom in" onClick={() => ui.set({ zoom: Math.min(12, ui.zoom * 1.25) })}>
                <Icon name="zoomIn" size={15} />
              </button>
              <button className="btn sm icon" aria-label="Fit to screen" title="Fit" onClick={() => ui.set({ zoom: 1, pan: { x: 0, y: 0 } })}>
                <Icon name="fit" size={15} />
              </button>
              <label className="row small" title="Show placement reference points">
                <input type="checkbox" checked={ui.showAnchors} onChange={(e) => ui.set({ showAnchors: e.target.checked })} /> Reference points
              </label>
            </>
          )}
        </div>
        {ui.preview === 'technical' ? <EditorCanvas /> : <GhostPreview />}
      </section>
      <Inspector />
    </div>
  );
}
