/**
 * Records a content hash for every published template version in
 * src/shared/templates/published-lock.json. Published versions are immutable: if a hash
 * changes, the test suite fails — create a new template version instead of editing one.
 * Only run this when publishing a NEW version: npx tsx scripts/lock-templates.ts
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import { allTemplateVersions } from '../src/shared/templates';

const file = 'src/shared/templates/published-lock.json';
const lock: Record<string, string> = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {};
for (const t of allTemplateVersions()) {
  const key = `${t.id}@${t.version}`;
  const hash = crypto.createHash('sha256').update(JSON.stringify(t)).digest('hex');
  if (lock[key] && lock[key] !== hash) {
    console.error(`Refusing to overwrite ${key}: published geometry changed. Bump the version instead.`);
    process.exit(1);
  }
  lock[key] = hash;
}
fs.writeFileSync(file, JSON.stringify(lock, null, 2) + '\n');
console.log(`Locked ${Object.keys(lock).length} template version(s).`);
