// Runs the commands of the last step of "Build an adapter step by step" on
// an engine of the repository, so that the page shows no command the
// program does not take. Run after the build: `npm run check:first-run`.
//
// The page shows the first run of the reader's engine with words between
// `<` and `>` in the places the reader fills in. This script reads the
// commands of that step from the built page of each language, puts the
// engine of `examples/toy_engine/` in those places, and runs them from the
// repository root with `uv run deltarecon`, writing into a temporary folder
// outside the repository. It needs `uv` and the checkout, so it is no part
// of `npm run check`.
//
// For the page of each language:
//   - the step holds two commands per platform, `request` and `run`; the
//     Windows command is the Linux command apart from the name of the
//     program and the path separators;
//   - with the engine put in, both commands end with exit status 0, and the
//     folder of the run then holds every file the file list of the step
//     names;
//   - the smallest compare request the step shows, filled in for this run
//     and a second one of another revision, is a request `compare` reads: it
//     writes its result;
//   - the page does not name the engine this script runs.
// A command that fails is printed with what it wrote to its outputs.
//
// Exits non-zero and names page and part of every failed expectation.
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';
import { expectations, loadPages, root, startPreview } from './harness.mjs';

const PAGE = 'build-an-adapter';
const STEP = 'first-run';
const repository = path.resolve(root, '..');
/** The program as the page of each platform starts it, and as a checkout does. */
const PROGRAM = { windows: '.\\deltarecon.cmd', linux: './deltarecon' };
const CHECKOUT = ['uv', 'run', 'deltarecon'];
/**
 * What stands in the place of each word of the page: the engine of
 * `examples/toy_engine/`, its stage and two of its revisions. `<output>` is
 * the folder of a run in the temporary folder. The German page writes some
 * of the words in German; both forms stand here.
 */
const ENGINE = {
  '<module>:<class>': 'toy_engine:ToyEngine',
  '<folder>': 'examples/toy_engine',
  '<stage>': 'toy_premium',
  '<Stufe>': 'toy_premium',
};
const RUNS = [
  { name: 'older', '<revision>': 'r1', '<label>': 'r1', '<run-id>': 'run-r1', '<Revision>': 'r1', '<Bezeichnung>': 'r1', '<Lauf-ID>': 'run-r1' },
  { name: 'newer', '<revision>': 'r2', '<label>': 'r2', '<run-id>': 'run-r2', '<Revision>': 'r2', '<Bezeichnung>': 'r2', '<Lauf-ID>': 'run-r2' },
];
/** A word of the page that names the engine of this script. */
const NAMED = /\btoy/i;

const { failures, expect, report } = expectations('check-first-run');

/** A command line with each word of `words` replaced; the words left over. */
function fill(line, words) {
  let filled = line;
  for (const [word, value] of Object.entries(words)) filled = filled.replaceAll(word, value);
  return { filled, left: filled.match(/<[^<>\s]*>/g) ?? [] };
}

/** Runs a command of the page in the checkout; says how it ended. */
function run(line) {
  const [program, ...args] = line.split(/\s+/);
  if (program !== PROGRAM.linux || /["'$`\\]/.test(line)) {
    return { status: null, output: 'the command does not start the program of the package, or it holds a quotation mark, a variable or a backslash' };
  }
  const result = spawnSync(CHECKOUT[0], [...CHECKOUT.slice(1), ...args], { cwd: repository, encoding: 'utf8' });
  return { status: result.status, output: `${result.stdout ?? ''}${result.stderr ?? ''}${result.error ? result.error.message : ''}` };
}

/** What the last step of the page shows. */
function readStep(page) {
  return page.evaluate((step) => {
    const card = document.getElementById(step);
    const commands = (platform) =>
      (card?.querySelector(`[data-platform-switch] > [data-platform-part="${platform}"] [data-copy]`)?.dataset.copy ?? '')
        .split('\n')
        .filter(Boolean);
    return {
      found: card !== null,
      windows: commands('windows'),
      linux: commands('linux'),
      files: [...(card?.querySelectorAll('[data-file-list] [data-file-name]') ?? [])].map((file) => file.textContent.trim()),
      document: card?.querySelector('[data-document]')?.dataset.copy ?? '',
      text: document.querySelector('main')?.innerHTML ?? '',
    };
  }, STEP);
}

/** The first run of one page: both commands, twice, and the comparison. */
async function checkPage(name, shown, folder) {
  expect(shown.found, `${name}: no step "${STEP}"`);
  expect(!NAMED.test(shown.text), `${name}: the page names the engine this script runs (${NAMED})`);
  expect(
    shown.linux.length === 2 && / request /.test(shown.linux[0] ?? '') && / run /.test(shown.linux[1] ?? ''),
    `${name}, step "${STEP}": the commands for Linux are not "request" and then "run": ${JSON.stringify(shown.linux)}`,
  );
  expect(
    shown.windows.length === shown.linux.length &&
      shown.windows.every((line, index) => line.replace(PROGRAM.windows, PROGRAM.linux).replaceAll('\\', '/') === shown.linux[index]),
    `${name}, step "${STEP}": a command for Windows is not the command for Linux apart from the program and the path separators: ${JSON.stringify(shown.windows)}`,
  );
  if (shown.linux.length !== 2) return;

  const outputs = [];
  for (const entry of RUNS) {
    const { name: runName, ...words } = entry;
    const output = path.join(folder, runName);
    outputs.push(output);
    for (const line of shown.linux) {
      const { filled, left } = fill(line, { ...ENGINE, ...words, '<output>': output, '<Ausgabe>': output });
      if (left.length > 0) {
        failures.push(`${name}, step "${STEP}": the script has nothing to put in the place of ${left.join(', ')} in "${line}"`);
        return;
      }
      const { status, output: printed } = run(filled);
      if (status !== 0) {
        failures.push(`${name}, step "${STEP}": the command ended with exit status ${status}, expected 0:\n      ${filled}\n      ${printed.trim().split('\n').join('\n      ')}`);
        return;
      }
    }
    for (const file of shown.files) {
      expect(existsSync(path.join(output, file)), `${name}, step "${STEP}": the file list names ${file}, which the two commands did not write`);
    }
    expect(shown.files.length > 0, `${name}, step "${STEP}": the file list names no file`);
  }

  // The smallest compare request of the page, for the two runs.
  const sums = await Promise.all(
    outputs.map(async (output) => createHash('sha256').update(await readFile(path.join(output, 'response.json'))).digest('hex')),
  );
  let request = fill(shown.document, { '<stage>': ENGINE['<stage>'], '<Stufe>': ENGINE['<stage>'], '<id>': 'first-run', '<ID>': 'first-run', '<older>': RUNS[0].name, '<älter>': RUNS[0].name, '<newer>': RUNS[1].name, '<neuer>': RUNS[1].name }).filled;
  for (const sum of sums) request = request.replace('<sha256>', sum);
  const left = request.match(/<[^<>\s]*>/g) ?? [];
  expect(shown.document !== '' && left.length === 0, `${name}, step "${STEP}": no compare request, or the script has nothing to put in the place of ${left.join(', ')}`);
  if (shown.document === '' || left.length > 0) return;
  const requestPath = path.join(folder, 'compare.json');
  await writeFile(requestPath, request);
  const compared = spawnSync(CHECKOUT[0], [...CHECKOUT.slice(1), 'compare', requestPath], { cwd: repository, encoding: 'utf8' });
  // Status 1 says that the two runs differ; the request was read.
  let outcome;
  try {
    outcome = JSON.parse(await readFile(path.join(folder, 'compare.result.json'), 'utf8')).outcome;
  } catch {
    outcome = undefined;
  }
  expect(
    (compared.status === 0 || compared.status === 1) && outcome === 'compared',
    `${name}, step "${STEP}": "compare" does not compare the two runs with the compare request of the page (exit status ${compared.status}, outcome ${outcome}):\n      ${request.split('\n').join('\n      ')}\n      ${`${compared.stdout ?? ''}${compared.stderr ?? ''}`.trim().split('\n').join('\n      ')}`,
  );
}

let checked = 0;
try {
  execFileSync(CHECKOUT[0], ['--version'], { stdio: 'ignore' });
} catch {
  failures.push('the program "uv" does not start; this check runs the commands of the page with "uv run deltarecon" in the checkout');
}
if (failures.length === 0) {
  const pages = (await loadPages()).filter((entry) => entry.id === PAGE);
  expect(pages.length === 2, `the page "${PAGE}" is not in the page register once per language`);
  const { origin: reported, stop } = startPreview();
  let browser;
  try {
    const origin = await reported;
    browser = await chromium.launch();
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    for (const entry of pages) {
      await page.goto(`${origin}${entry.address}`);
      const shown = await readStep(page);
      const folder = await mkdtemp(path.join(os.tmpdir(), 'docs-first-run-'));
      try {
        await checkPage(entry.address, shown, folder);
        checked += 1;
      } finally {
        await rm(folder, { recursive: true, force: true });
      }
    }
    await context.close();
  } catch (error) {
    failures.push(error.stack ?? error.message);
  } finally {
    await browser?.close();
    stop();
  }
}

report(`on ${checked} pages the two commands of the step "${STEP}" end with exit status 0 on the engine of examples/toy_engine, for two revisions, and "compare" reads the compare request of the page`);
