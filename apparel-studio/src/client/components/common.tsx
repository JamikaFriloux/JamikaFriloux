import React, { useEffect, useState } from 'react';
import type { LengthUnit } from '../../shared/units';
import { formatLength, parseLength } from '../../shared/units';
import { useUi } from '../store/ui';
import { useProject } from '../store/project';
import { Icon } from './Icon';
import type { AssetResolver } from '../../shared/render/TechView';
import type { ProjectDoc } from '../../shared/schema/project';
import { blobUrl } from '../api';

/**
 * Physical length input. Shows the canonical mm value in the chosen display unit and only
 * writes back when the user commits an edit (Enter/blur) — switching units never rewrites data.
 */
export function LengthInput({
  mm,
  unit,
  onCommit,
  allowEmpty = false,
  min,
  className = 'input',
  ariaLabel,
  placeholder,
  isDefault,
}: {
  mm: number | null;
  unit: LengthUnit;
  onCommit: (mm: number | null) => void;
  allowEmpty?: boolean;
  min?: number;
  className?: string;
  ariaLabel?: string;
  placeholder?: string;
  isDefault?: boolean;
}) {
  const shown = formatLength(mm, unit, { withUnit: false, fractions: unit === 'in' });
  const [text, setText] = useState(shown);
  const [editing, setEditing] = useState(false);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    if (!editing) {
      setText(shown);
      setInvalid(false);
    }
  }, [shown, editing]);
  const commit = () => {
    setEditing(false);
    if (text.trim() === '') {
      if (allowEmpty) {
        if (mm !== null) onCommit(null);
        setInvalid(false);
      } else {
        setText(shown);
      }
      return;
    }
    if (text === shown) return;
    const v = parseLength(text, unit);
    if (v === null || (min !== undefined && v < min)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onCommit(v);
  };
  return (
    <input
      className={`${className}${invalid ? ' invalid' : ''}${isDefault ? ' default' : ''}`}
      value={text}
      inputMode="decimal"
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      title={invalid ? `Enter a number in ${unit}${unit === 'in' ? ' (e.g. 12.5 or 12 1/2)' : ''}` : isDefault ? 'Template default — not confirmed' : undefined}
      placeholder={placeholder ?? (allowEmpty ? '—' : '')}
      onFocus={() => setEditing(true)}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        if (e.key === 'Escape') {
          setText(shown);
          setEditing(false);
          setInvalid(false);
          (e.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}

export function NumberInput({ value, onCommit, step = 1, min, max, ariaLabel, suffix }: { value: number; onCommit: (v: number) => void; step?: number; min?: number; max?: number; ariaLabel?: string; suffix?: string }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(Math.round(value * 100) / 100)), [value]);
  const commit = () => {
    const v = Number(text);
    if (!Number.isFinite(v)) return setText(String(value));
    const c = Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v));
    if (c !== value) onCommit(c);
    setText(String(c));
  };
  return (
    <div className="row" style={{ gap: 4 }}>
      <input className="input" type="number" step={step} min={min} max={max} value={text} aria-label={ariaLabel} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && commit()} />
      {suffix && <span className="small muted">{suffix}</span>}
    </div>
  );
}

export function TextInput({ value, onCommit, ariaLabel, multiline, placeholder }: { value: string; onCommit: (v: string) => void; ariaLabel?: string; multiline?: boolean; placeholder?: string }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => text !== value && onCommit(text);
  return multiline ? (
    <textarea className="input" value={text} aria-label={ariaLabel} placeholder={placeholder} onChange={(e) => setText(e.target.value)} onBlur={commit} />
  ) : (
    <input className="input" value={text} aria-label={ariaLabel} placeholder={placeholder} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
  );
}

export function SaveStatus() {
  const { saveState, saveError, retrySave } = useProject();
  const label = { saved: 'All changes saved', dirty: 'Unsaved changes…', saving: 'Saving…', error: 'Save failed', conflict: 'Changed elsewhere' }[saveState];
  return (
    <div className="save-status" role="status" aria-live="polite" title={saveError ?? undefined} data-testid="save-status" data-state={saveState}>
      <span className={`save-dot ${saveState}`} />
      {label}
      {saveState === 'error' && (
        <button className="btn sm" onClick={retrySave}>
          Retry
        </button>
      )}
      {saveState === 'conflict' && (
        <button className="btn sm" onClick={() => window.location.reload()}>
          Reload
        </button>
      )}
    </div>
  );
}

export function Toast() {
  const { toast, set } = useUi();
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => set({ toast: null }), toast.kind === 'error' ? 9000 : 5000);
    return () => clearTimeout(t);
  }, [toast, set]);
  if (!toast) return null;
  return (
    <div className={`toast callout ${toast.kind === 'error' ? 'err' : toast.kind === 'warn' ? 'warn' : 'info'}`} role="alert">
      <div className="row">
        <span style={{ flex: 1 }}>{toast.text}</span>
        <button className="btn sm ghost icon" aria-label="Dismiss" onClick={() => set({ toast: null })}>
          <Icon name="x" />
        </button>
      </div>
    </div>
  );
}

export function useAssetResolver(doc: ProjectDoc | null): AssetResolver {
  return (assetId) => {
    const a = doc?.assets.find((x) => x.id === assetId);
    return a ? { kind: 'href', href: blobUrl(a.sha256) } : { kind: 'missing' };
  };
}

export function Modal({ title, onClose, children, footer, width = 520 }: { title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode; width?: number }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,18,24,0.45)', display: 'grid', placeItems: 'center', zIndex: 50, padding: 16 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card" role="dialog" aria-modal="true" aria-label={title} style={{ width, maxWidth: '100%', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
        <div className="section row">
          <h2 style={{ flex: 1 }}>{title}</h2>
          <button className="btn ghost icon" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="section" style={{ overflow: 'auto' }}>
          {children}
        </div>
        {footer && (
          <div className="section row" style={{ justifyContent: 'flex-end' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
