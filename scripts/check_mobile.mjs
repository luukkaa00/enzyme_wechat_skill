#!/usr/bin/env node
// Local preview checks; screenshots still require human review.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const args = process.argv.slice(2);
const flag = args.indexOf('--output-dir');
let outputDir = path.resolve('tmp/wechat-mobile-check');
if (flag !== -1) {
  if (!args[flag + 1]) throw new Error('--output-dir needs a directory');
  outputDir = path.resolve(args[flag + 1]);
  args.splice(flag, 2);
}
if (!args.length || args.some(a => a.startsWith('--'))) {
  process.stderr.write('Usage: node check_mobile.mjs preview.html [wechat.html] [--output-dir DIRECTORY]\n');
  process.exit(2);
}
await fs.mkdir(outputDir, { recursive: true });
const report = { status: 'unverified', widths: [375, 390], files: [], human_visual_review_required: true };
let browser;
try {
  const require = createRequire(import.meta.url);
  const { chromium } = require('playwright');
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
} catch (error) {
  report.reason = 'browser_unavailable';
  report.detail = String(error.message).split('\n')[0];
}
if (browser) {
  try {
    for (const [index, input] of args.entries()) {
      const file = path.resolve(input);
      for (const width of report.widths) {
        const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 1 });
        try {
          await page.goto(pathToFileURL(file).href, { waitUntil: 'load', timeout: 15000 });
          await page.evaluate(() => document.fonts.ready);
          const metrics = await page.evaluate(() => {
            const main = document.body.firstElementChild;
            const paragraphs = [...main.querySelectorAll('p')].filter(el => el.style.textIndent === '2em');
            return {
              horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 1,
              broken_images: [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.alt),
              headings_outside_viewport: [...document.querySelectorAll('h1,h2,h3')].filter(el => {
                const r = el.getBoundingClientRect();
                return r.left < -1 || r.right > innerWidth + 1 || el.scrollWidth > el.clientWidth + 1;
              }).map(el => el.textContent.trim() || el.querySelector('svg')?.getAttribute('aria-label')),
              long_paragraphs: paragraphs.filter(el => el.getBoundingClientRect().height > 400).map(el => el.textContent.slice(0, 40)),
              figure_display_widths: [...document.querySelectorAll('figure img')].map(el => Math.round(el.getBoundingClientRect().width))
            };
          });
          const screenshot = path.join(outputDir, `${index + 1}_${width}.png`);
          await page.screenshot({ path: screenshot, fullPage: true });
          report.files.push({ file, width, screenshot, ...metrics });
        } catch (error) {
          report.files.push({ file, width, error: String(error.message).split('\n')[0] });
        } finally {
          await page.close();
        }
      }
    }
    report.status = report.files.some(r => r.error || r.horizontal_overflow || r.broken_images.length || r.headings_outside_viewport.length)
      ? 'failed' : 'automated_checks_passed';
  } finally {
    await browser.close();
  }
}
await fs.writeFile(path.join(outputDir, 'report.json'), JSON.stringify(report, null, 2));
process.stdout.write(JSON.stringify(report) + '\n');
if (report.status === 'failed') process.exitCode = 1;
