// Writes what the company website needs to take the documentation with its
// own build. Runs as the last step of `npm run build`.
//
//   - dist/sitemap.xml: the 22 pages of the page register with their absolute
//     addresses, each with its `de` and `en` versions. The root page and the
//     page-not-found pages are not listed.
//   - dist/delivery.json, the delivery record: the commit the build was made
//     from (`commit`), whether the working tree of the repository differed
//     from that commit (`changed`; an untracked file that Git does not ignore
//     counts, because pages quote files of the repository), and per page of
//     the register its language, absolute address, name and the description
//     of its built head (`pages`). The website compares `commit` with the
//     commit it has accepted, refuses a build with `changed: true`, and does
//     not publish the record.
//
// Exits non-zero when a page of the register is not built, when a built page
// holds no description or more than one, and when Git does not answer.
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { BASE, loadPages, root } from './harness.mjs';

const SITE = 'https://degelmann-solutions.de';
const dist = path.join(root, 'dist');

function stopWith(message) {
  console.error(`write-delivery: ${message}`);
  process.exit(1);
}

function git(...args) {
  try {
    return execFileSync('git', args, { cwd: root, encoding: 'utf8' });
  } catch (error) {
    return stopWith(`git ${args.join(' ')} failed: ${error.message}`);
  }
}

/** The text of an attribute value as the built page writes it. */
function decode(value) {
  return value
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function escapeXml(value) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** The description of the head of a built page of the register. */
async function descriptionOf(entry) {
  const file = path.join(dist, entry.address.slice(BASE.length), 'index.html');
  let html;
  try {
    html = await readFile(file, 'utf8');
  } catch (error) {
    return stopWith(`${entry.address}: in the page register, but not built (${error.message})`);
  }
  const found = [...html.matchAll(/<meta\s+name="description"\s+content="([^"]*)"/g)];
  if (found.length !== 1 || decode(found[0][1]).trim() === '') {
    return stopWith(`${entry.address}: the built page holds ${found.length} descriptions, expected one that is not empty`);
  }
  return decode(found[0][1]);
}

const pages = await loadPages();

const record = {
  commit: git('rev-parse', 'HEAD').trim(),
  changed: git('status', '--porcelain').trim() !== '',
  pages: [],
};
for (const entry of pages) {
  record.pages.push({
    lang: entry.lang,
    address: `${SITE}${entry.address}`,
    title: entry.name,
    description: await descriptionOf(entry),
  });
}

const urls = pages.map((entry) => {
  const versions = { [entry.lang]: entry.address, [entry.otherLang]: entry.counterpart };
  const links = ['de', 'en'].map(
    (lang) =>
      `    <xhtml:link rel="alternate" hreflang="${lang}" href="${escapeXml(`${SITE}${versions[lang]}`)}"/>`,
  );
  return `  <url>\n    <loc>${escapeXml(`${SITE}${entry.address}`)}</loc>\n${links.join('\n')}\n  </url>`;
});
const sitemap =
  '<?xml version="1.0" encoding="UTF-8"?>\n' +
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' +
  `${urls.join('\n')}\n</urlset>\n`;

await writeFile(path.join(dist, 'sitemap.xml'), sitemap);
await writeFile(path.join(dist, 'delivery.json'), `${JSON.stringify(record, null, 2)}\n`);
console.log(
  `write-delivery: sitemap.xml and delivery.json for ${pages.length} pages, commit ${record.commit}, working tree ${record.changed ? 'changed' : 'unchanged'}`,
);
