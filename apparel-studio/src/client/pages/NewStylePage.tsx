import React, { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listTemplates } from '../../shared/templates';
import { createProjectDoc } from '../../shared/domain/factory';
import { TechView } from '../../shared/render/TechView';
import { api } from '../api';
import { Icon } from '../components/Icon';

export function NewStylePage() {
  const templates = listTemplates();
  const [templateId, setTemplateId] = useState(templates[0]?.id ?? '');
  const [name, setName] = useState('');
  const [styleNumber, setStyleNumber] = useState('');
  const [collection, setCollection] = useState('');
  const [season, setSeason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const previews = useMemo(() => Object.fromEntries(templates.map((t) => [t.id, createProjectDoc(t, { name: 'preview', styleNumber: 'x' })])), [templates]);
  const chosen = templates.find((t) => t.id === templateId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const rec = await api.createProject({ templateId, name: name.trim(), styleNumber: styleNumber.trim(), collection: collection.trim(), season: season.trim() });
      navigate(`/p/${rec.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="btn ghost sm">
          <Icon name="back" /> All styles
        </Link>
        <h2>New style</h2>
      </header>
      <main className="page">
        <form className="page-inner" onSubmit={submit}>
          <h2 style={{ marginBottom: 6 }}>1. Choose a garment</h2>
          <p className="hint" style={{ marginBottom: 14 }}>
            Each garment is a versioned technical template with named parts you can customize individually.
          </p>
          <div className="garment-grid" role="radiogroup" aria-label="Garment">
            {templates.map((t) => {
              const doc = previews[t.id];
              return (
                <button type="button" key={t.id} className="card garment-card" aria-pressed={t.id === templateId} role="radio" aria-checked={t.id === templateId} onClick={() => setTemplateId(t.id)} data-testid={`garment-${t.id}`}>
                  <div className="row">
                    <h3 style={{ flex: 1 }}>{t.name}</h3>
                    {t.ghost ? (
                      <span className="badge info" title={t.ghost.notes}>
                        Realistic preview: {t.ghost.quality === 'photographic' ? 'photographic' : 'procedural assets'}
                      </span>
                    ) : (
                      <span className="badge warn">Technical view only</span>
                    )}
                  </div>
                  <div className="views">
                    {t.views.map((v) => (
                      <div key={v.id}>
                        <TechView template={t} doc={doc} viewId={v.id} resolveAsset={() => ({ kind: 'missing' })} idPrefix={`ns-${t.id}`} textures={false} />
                        <div className="small muted" style={{ textAlign: 'center' }}>
                          {v.label}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="small muted" style={{ marginBottom: 6 }}>
                    {t.description}
                  </p>
                  <div className="small">
                    <strong>Editable parts:</strong> {t.components.map((c) => c.name).join(', ')}
                  </div>
                  <div className="small muted" style={{ marginTop: 4 }}>
                    {t.poms.length} measurement points · {t.views.reduce((a, v) => a + v.seams.length, 0)} seam paths · template v{t.version}
                  </div>
                </button>
              );
            })}
          </div>

          <h2 style={{ margin: '26px 0 10px' }}>2. Name your style</h2>
          <div className="card" style={{ padding: 16, maxWidth: 640 }}>
            <div className="grid2">
              <div className="field">
                <label htmlFor="sn">Style name *</label>
                <input id="sn" className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sunset Club Tee" />
              </div>
              <div className="field">
                <label htmlFor="snum">Style number *</label>
                <input id="snum" className="input" required value={styleNumber} onChange={(e) => setStyleNumber(e.target.value)} placeholder="e.g. SC-TS-002" />
              </div>
              <div className="field">
                <label htmlFor="col">Collection / set</label>
                <input id="col" className="input" value={collection} onChange={(e) => setCollection(e.target.value)} placeholder="Optional — groups styles" />
              </div>
              <div className="field">
                <label htmlFor="sea">Season</label>
                <input id="sea" className="input" value={season} onChange={(e) => setSeason(e.target.value)} placeholder="e.g. FW27" />
              </div>
            </div>
            {error && <div className="callout err" style={{ marginBottom: 10 }}>{error}</div>}
            <button className="btn primary" type="submit" disabled={busy || !name.trim() || !styleNumber.trim() || !chosen}>
              Create {chosen?.name ?? 'style'}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
