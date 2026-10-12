/** Dev helper: write a template's front/back technical views as standalone SVG files. Usage: npx tsx scripts/render-template.tsx <templateId> <outDir> */
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { listTemplates } from '../src/shared/templates';
import { createProjectDoc } from '../src/shared/domain/factory';
import { TechView } from '../src/shared/render/TechView';

const [id, out = '.'] = process.argv.slice(2);
const t = listTemplates().find((x) => x.id === id)!;
const doc = createProjectDoc(t, { name: 'x', styleNumber: 'x' });
const codes = Object.fromEntries(t.poms.map((p) => [p.id, p.code]));
for (const v of t.views) {
  for (const mode of ['flat', 'pom'] as const) {
    const svg = renderToStaticMarkup(
      React.createElement(TechView, { template: t, doc, viewId: v.id, resolveAsset: () => ({ kind: 'missing' }), anchors: mode === 'flat', measurements: mode === 'pom' ? { pomCodes: codes } : undefined, fills: mode === 'flat', width: 900 }),
    );
    fs.writeFileSync(path.join(out, `${id}-${v.id}-${mode}.svg`), svg);
  }
}
