import type { RevisionSnapshot } from './revisions';
import { colorwayNames } from '../../shared/domain/bom';
import { formatLength } from '../../shared/units';

/** RFC 4180 cell with spreadsheet-formula injection protection. */
export function csvCell(v: unknown): string {
  let s = v === null || v === undefined ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: unknown[][]): string {
  return '﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
}

export function bomCsv(snap: RevisionSnapshot): string {
  const header = ['Style number', 'Revision', 'Category', 'Component', 'Material / trim', 'Description', 'Quantity', 'Unit', 'Quantity type', 'Colorways', 'Supplier ref', 'Notes', 'Source'];
  const rows = snap.bom.map((b) => [
    snap.doc.styleNumber,
    snap.label,
    b.category,
    b.component,
    b.materialName,
    b.description,
    b.quantity ?? '',
    b.unit,
    b.quantityType === 'missing' ? 'not entered' : b.quantityType,
    colorwayNames(snap.doc, b.colorwayIds),
    b.supplierRef,
    b.notes,
    b.derived ? `derived from design (${b.source})` : 'entered manually',
  ]);
  return toCsv([header, ...rows]);
}

export function measurementsCsv(snap: RevisionSnapshot): string {
  const unit = snap.doc.displayUnit;
  const sizes = snap.doc.sizes.range;
  const header = [
    'Style number',
    'Revision',
    'POM',
    'Description',
    'How to measure',
    `Tolerance - (${unit})`,
    `Tolerance + (${unit})`,
    ...sizes.map((s) => `${s}${s === snap.doc.sizes.base ? ' (base)' : ''} (${unit})`),
    'Status',
    'Source',
  ];
  const rows = snap.doc.measurements.map((p) => {
    const hasDefault = Object.values(p.values).some((v) => v.source === 'template-default');
    return [
      snap.doc.styleNumber,
      snap.label,
      p.code,
      p.label,
      p.howToMeasure,
      formatLength(p.tolMinusMm, unit, { withUnit: false }),
      formatLength(p.tolPlusMm, unit, { withUnit: false }),
      ...sizes.map((s) => formatLength(p.values[s]?.mm ?? null, unit, { withUnit: false })),
      p.confirmed ? 'Confirmed' : hasDefault ? 'Template default - unconfirmed' : 'Unconfirmed',
      p.source,
    ];
  });
  return toCsv([header, ...rows]);
}
