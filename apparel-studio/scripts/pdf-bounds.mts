// Dev/verification helper: report text outside the page and overlapping text for a PDF.
import fs from 'node:fs';
import { readPdf, textOverlaps } from '../tests/pdfText.ts';
const pages = await readPdf(fs.readFileSync(process.argv[2]));
let problems = 0;
pages.forEach((p, i) => {
  for (const it of p.items.filter((it) => it.str.trim() && (it.x < 0 || it.y < 0 || it.x + it.w > p.width || it.y + it.h > p.height))) {
    problems++;
    console.log(`page ${i + 1}: outside page: ${JSON.stringify(it)}`);
  }
  for (const o of textOverlaps(p)) {
    problems++;
    console.log(`page ${i + 1}: overlap ${o}`);
  }
});
console.log(`pages ${pages.length}, problems ${problems}`);
