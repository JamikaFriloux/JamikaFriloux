import fs from 'node:fs';
import { readPdf } from '../tests/pdfText.ts';
const pages = await readPdf(fs.readFileSync(process.argv[2]));
pages.forEach((p, i) => p.items.filter((it) => it.str.trim() && (it.x < 0 || it.y < 0 || it.x + it.w > p.width || it.y + it.h > p.height)).forEach((it) => console.log(i + 1, JSON.stringify(it))));
console.log('pages', pages.length);
