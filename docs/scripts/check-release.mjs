// Holds what the step pages show against the release they describe. It
// needs what is not under version control, so it is not part of
// `npm run check`:
//
//   npm run check:release -- --search <search folder of a run of the demo>
//
//   - `../dist/release-v<version>/`, the folder of the published release:
//     `release-notes.md`, `SHA256SUMS`, both unpacked packages with their
//     guides `README.txt` and `LIESMICH.txt`. Without it the check fails.
//   - `--search <folder>`: the folder `search/` of a run of the guided demo
//     of that release. Its `search.result.json` must have the SHA-256 the
//     pin names (`../measurements/quick-start-search.SHA256SUMS`).
//
// First, without a build, the capture files (src/captures/v<version>/):
//   - the four files are there; the Windows and the Linux capture of a
//     language equal each other line by line once path separators and the
//     time stamp of the demo folder are set aside (and the line the Windows
//     starter prints at its end);
//   - the table of the search in each file names the revisions and sums of
//     `search.result.json`, in the number format of the language; the line
//     above it names its counts of computations; the "Not resolved" message
//     names the revisions of its finding.
// A difference is named with file and line. Then it builds the site and
// asserts on the built step pages of both languages, with JavaScript off, so
// that both platforms' parts are in the page:
//   - every command stands in a guide of the release. Steps 1 to 3: in the
//     release notes, as a line of a code block or as inline code, where
//     `<zip>` stands for the Windows archive and an option may follow a
//     command when the same paragraph of the notes names both; else in the
//     README of the release, which the notes point to
//     (`git show v<version>:README.md`). From step 4 on: in the guide of the
//     page's language in the package of the platform, else as a line of a
//     code block of the release notes. The command of a terminal block is a
//     command of the guide with `--lang <language>`, which the guide names;
//   - the names of archives and package folders and every SHA-256 on the
//     page are those of `SHA256SUMS`, and `src/release.json` holds the same
//     sums; the file list of the package folder names, per platform, exactly
//     the entries of the unpacked package, a folder with a closing slash;
//   - output on the page stands in the capture of that language: the
//     terminal session line by line, the lines of the summary list, the
//     caption, head and rows of the result table, the "Not resolved"
//     message; table and bar figure show the revisions and sums of
//     `search.result.json`.
// Exits non-zero and names what differs.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import { expectations, loadPages, loadRelease, root, startPreview } from './harness.mjs';

const LANGUAGES = ['en', 'de'];
const PLATFORMS = ['windows', 'linux'];
/** The guide of a package in each language. */
const GUIDES = { en: 'README.txt', de: 'LIESMICH.txt' };
/** What the lines of a capture begin with, per language. */
const MARKERS = {
  en: { step: (number) => `Step ${number} of 4: `, notResolved: 'Not resolved:', locale: 'en-US' },
  de: { step: (number) => `Schritt ${number} von 4: `, notResolved: 'Nicht aufgelöst:', locale: 'de-DE' },
};
/** The quantity the search of the demo looks at. */
const QUANTITY = 'Bruttobeitrag';

const repository = path.resolve(root, '..');
const version = await loadRelease();
const releaseFolder = path.join(repository, 'dist', `release-v${version}`);
const captureFolder = path.join('src', 'captures', `v${version}`);
const pin = path.join(repository, 'measurements', 'quick-start-search.SHA256SUMS');
const { failures, expect, report } = expectations('check-release');

const read = (file) => readFile(file, 'utf8');
const squash = (text) => text.replace(/\s+/g, ' ').trim();
const relative = (file) => path.relative(repository, file);

/** `SHA256SUMS`: the SHA-256 of each named file. */
function parseSums(text) {
  return new Map(
    text
      .split('\n')
      .map((line) => /^([0-9a-f]{64}) [ *](.+)$/.exec(line.trim()))
      .filter(Boolean)
      .map(([, sum, file]) => [file, sum]),
  );
}

/** A sum of the search as the demo prints it in a language. */
function printed(sum, lang) {
  const digits = Math.abs(sum).toLocaleString(MARKERS[lang].locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sum < 0 ? '-' : '+'}${digits}`;
}

/**
 * The commands a text names: `all`, the lines of fenced code blocks and the
 * inline code; `blocks`, the lines of code blocks alone; `paragraphs`, the
 * inline code of each paragraph (a run of lines between blank lines).
 */
function commandsOfMarkdown(text) {
  const all = new Set();
  const blocks = new Set();
  const paragraphs = [new Set()];
  let fenced = false;
  for (const line of text.split('\n')) {
    if (line.trimStart().startsWith('```')) {
      fenced = !fenced;
    } else if (fenced) {
      if (line.trim() !== '') {
        all.add(line.trim());
        blocks.add(line.trim());
      }
    } else if (line.trim() === '') {
      paragraphs.push(new Set());
    } else {
      for (const [, code] of line.matchAll(/`([^`]+)`/g)) {
        all.add(code.trim());
        paragraphs.at(-1).add(code.trim());
      }
    }
  }
  return { all, blocks, paragraphs };
}

/** The commands of a package guide: its indented lines. */
function commandsOfGuide(text) {
  return new Set(
    text
      .split('\n')
      .filter((line) => /^ {4}\S/.test(line))
      .map((line) => line.trim()),
  );
}

// ---- What the check needs ----

const searchAt = process.argv.indexOf('--search');
const searchFolder = searchAt === -1 ? undefined : process.argv[searchAt + 1];
if (!existsSync(releaseFolder)) {
  failures.push(
    `${relative(releaseFolder)}: the folder of the release ${version} is missing; the check needs its release notes, SHA256SUMS and both unpacked packages`,
  );
}
if (!searchFolder) {
  failures.push('no search folder: run `npm run check:release -- --search <folder search/ of a run of the demo>`');
} else if (!existsSync(path.join(searchFolder, 'search.result.json'))) {
  failures.push(`${searchFolder}: no search.result.json in the search folder`);
}
if (failures.length > 0) report('');

const sums = parseSums(await read(path.join(releaseFolder, 'SHA256SUMS')));
const archives = {
  windows: [...sums.keys()].find((file) => file.endsWith('.zip')),
  linux: [...sums.keys()].find((file) => file.endsWith('.tar.gz')),
};
const folders = {
  windows: archives.windows?.replace(/\.zip$/, ''),
  linux: archives.linux?.replace(/\.tar\.gz$/, ''),
};
for (const platform of PLATFORMS) {
  expect(Boolean(archives[platform]), `SHA256SUMS of the release names no archive for ${platform}`);
  expect(
    Boolean(folders[platform]) && existsSync(path.join(releaseFolder, folders[platform])),
    `${relative(releaseFolder)}: the unpacked package of ${platform} is missing`,
  );
}
if (failures.length > 0) report('');

// src/release.json holds the sums of the release.
const releaseData = JSON.parse(await read(path.join(root, 'src/release.json')));
for (const platform of PLATFORMS) {
  expect(
    releaseData.sha256?.[platform] === sums.get(archives[platform]),
    `src/release.json: sha256.${platform} is ${releaseData.sha256?.[platform]}, SHA256SUMS of the release names ${sums.get(archives[platform])} for ${archives[platform]}`,
  );
}

// The search result of the run, held against the pin.
const resultFile = path.join(searchFolder, 'search.result.json');
const resultText = await readFile(resultFile);
const pinned = parseSums(await read(pin)).get('search.result.json');
const digest = createHash('sha256').update(resultText).digest('hex');
expect(
  digest === pinned,
  `${resultFile}: SHA-256 ${digest}, the pin ${relative(pin)} names ${pinned}`,
);
const result = JSON.parse(resultText.toString('utf8'));
/** The revisions that deviate, with their sums, in the order of the result. */
const contributions = result.contributions.flatMap((interval) => {
  const sum = interval.contributions.find((entry) => entry.quantity === QUANTITY && entry.contributes)?.sum;
  return sum === undefined ? [] : [{ revision: interval.revisions.at(-1).slice(0, 7), sum }];
});
const notResolved = result.findings
  .filter((finding) => finding.code === 'interval_not_resolved')
  .map((finding) => finding.revisions.map((revision) => revision.slice(0, 7)));
const counts = [contributions.length, result.runs.search, result.runs.walk, result.runs.saved];
expect(contributions.length > 0, `${resultFile}: no revision contributes to ${QUANTITY}`);
const rowsOf = (lang) =>
  contributions.map(({ revision, sum }) => ({ revision, sum: printed(sum, lang) }));

// ---- The capture files ----

/** Sets aside what differs between the platforms: separators, the time stamp. */
const neutral = (line) =>
  line.replaceAll('\\', '/').replace(/quickstart-\d{8}T\d{6}Z/g, 'quickstart-<time>');

const captures = {};
for (const lang of LANGUAGES) {
  captures[lang] = {};
  for (const platform of PLATFORMS) {
    const file = path.join(captureFolder, `${platform}-${lang}.txt`);
    try {
      const lines = (await read(path.join(root, file))).replace(/\n$/, '').split('\n');
      captures[lang][platform] = { file: path.join('docs', file), lines };
    } catch {
      failures.push(`docs/${file}: the capture file is missing`);
    }
  }
}
if (failures.length > 0) report('');

for (const lang of LANGUAGES) {
  const { windows, linux } = captures[lang];
  // The Windows starter ends with the line of `pause`, which is not output
  // of the demo: one line more than the Linux capture.
  const windowsLines = windows.lines.length === linux.lines.length + 1 ? windows.lines.slice(0, -1) : windows.lines;
  expect(
    windowsLines.length === linux.lines.length,
    `${windows.file} has ${windows.lines.length} lines, ${linux.file} has ${linux.lines.length}; expected the same, or one more for the line the Windows starter ends with`,
  );
  for (let index = 0; index < Math.min(windowsLines.length, linux.lines.length); index += 1) {
    expect(
      neutral(windowsLines[index]) === neutral(linux.lines[index]),
      `${windows.file}:${index + 1} and ${linux.file}:${index + 1} differ beyond path separators and the time stamp: "${windowsLines[index].trim()}" and "${linux.lines[index].trim()}"`,
    );
  }

  for (const platform of PLATFORMS) {
    const { file, lines } = captures[lang][platform];
    const marker = MARKERS[lang];
    const start = lines.findIndex((line) => line.startsWith(marker.step(4)));
    if (start === -1) {
      failures.push(`${file}: no heading of step 4 ("${marker.step(4)}…")`);
      continue;
    }
    // The table: the lines that begin with a revision.
    const rows = [];
    lines.forEach((line, index) => {
      const row = /^ {2}([0-9a-f]{7}) {2}.*\s(\S+)$/.exec(line);
      if (index > start && row) rows.push({ line: index + 1, revision: row[1], sum: row[2] });
    });
    const expected = rowsOf(lang);
    expect(
      rows.length === expected.length,
      `${file}: the table of the search has ${rows.length} rows, search.result.json names ${expected.length} revisions`,
    );
    rows.forEach((row, index) => {
      const wanted = expected[index];
      if (!wanted) return;
      expect(
        row.revision === wanted.revision && row.sum === wanted.sum,
        `${file}:${row.line}: the table of the search shows ${row.revision} with ${row.sum}, search.result.json gives ${wanted.revision} with ${wanted.sum}`,
      );
    });
    // The line above the table: its numbers are the counts of the result.
    const first = rows[0]?.line;
    if (first) {
      let above = first - 3;
      while (above > start && lines[above - 1].trim() !== '') above -= 1;
      const paragraph = lines.slice(above, first - 2).join(' ');
      const numbers = [...paragraph.matchAll(/\d+/g)].map((match) => Number(match[0]));
      expect(
        numbers.join() === counts.join(),
        `${file}:${above + 1}: the line above the table names the numbers [${numbers}], search.result.json gives [${counts}] (revisions, computed, of, saved)`,
      );
    }
    // The "Not resolved" messages, one per finding.
    const messages = lines
      .map((line, index) => ({ line: index + 1, text: line }))
      .filter(({ text }) => text.startsWith(marker.notResolved));
    expect(
      messages.length === notResolved.length,
      `${file}: ${messages.length} messages "${marker.notResolved}", search.result.json holds ${notResolved.length} such findings`,
    );
    messages.forEach((message, index) => {
      const wanted = notResolved[index]?.join(', ');
      expect(
        Boolean(wanted) && message.text.includes(wanted),
        `${file}:${message.line}: the message does not name the revisions ${wanted} of the finding`,
      );
    });
  }
}
// A capture that differs fails here, with file and line, before the build.
if (failures.length > 0) report('');

// ---- The built pages ----

const build = spawnSync('npm', ['run', 'build'], { cwd: root, encoding: 'utf8' });
if (build.status !== 0) {
  failures.push(`the build failed:\n${build.stdout}\n${build.stderr}`);
  report('');
}

const notes = commandsOfMarkdown(await read(path.join(releaseFolder, 'release-notes.md')));
// The README of the release, which its notes point to: the file at the tag.
const tagged = spawnSync('git', ['show', `v${version}:README.md`], { cwd: repository, encoding: 'utf8' });
if (tagged.status !== 0) {
  failures.push(`git show v${version}:README.md failed; the check reads the README of the release: ${tagged.stderr.trim()}`);
  report('');
}
const readme = commandsOfMarkdown(tagged.stdout).all;
const guides = {};
const guideTexts = {};
for (const lang of LANGUAGES) {
  guides[lang] = {};
  guideTexts[lang] = {};
  for (const platform of PLATFORMS) {
    const text = await read(path.join(releaseFolder, folders[platform], GUIDES[lang]));
    guides[lang][platform] = commandsOfGuide(text);
    guideTexts[lang][platform] = text;
  }
}

/** Whether the release notes name a command of steps 1 to 3. */
function inNotes(command) {
  if (notes.all.has(command)) return true;
  // `<zip>` stands for the Windows archive.
  if (notes.all.has(command.replace(archives.windows, '<zip>'))) return true;
  // A command followed by an option, both named in one paragraph of the notes.
  const cut = command.lastIndexOf(' ');
  return (
    cut !== -1 &&
    notes.paragraphs.some(
      (paragraph) => paragraph.has(command.slice(0, cut)) && paragraph.has(command.slice(cut + 1)),
    )
  );
}

/** Where a command of the page stands, or nothing. */
function sourceOf(command, { step, platform, terminal }, lang) {
  if (terminal) {
    const option = ` --lang ${lang}`;
    const guide = guideTexts[lang][platform];
    return command.endsWith(option) &&
      guides[lang][platform].has(command.slice(0, -option.length)) &&
      guide.includes(option.trim())
      ? 'guide'
      : undefined;
  }
  if (step <= 3) return inNotes(command) ? 'release notes' : readme.has(command) ? 'README' : undefined;
  // From step 4 on the notes count only with a line of one of their code blocks.
  return guides[lang][platform].has(command) ? 'guide' : notes.blocks.has(command) ? 'release notes' : undefined;
}

const stepPages = (await loadPages()).filter((entry) => entry.id === 'quick-start');
const { origin: reported, stop } = startPreview();
let browser;
const found = { 'release notes': 0, README: 0, guide: 0 };
try {
  const origin = await reported;
  browser = await chromium.launch();
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  for (const entry of stepPages) {
    const name = entry.address;
    const lang = entry.lang;
    await page.goto(`${origin}${entry.address}`);
    const shown = await page.evaluate(() => {
      const steps = [...document.querySelectorAll('main [data-step]')];
      const text = (element) => element.textContent;
      return {
        commands: [...document.querySelectorAll('main [data-copy]')].map((block) => ({
          step: steps.indexOf(block.closest('[data-step]')) + 1,
          platform: block.closest('[data-platform-part]')?.dataset.platformPart,
          terminal: block.matches('[data-terminal]'),
          command: block.dataset.copy,
        })),
        sessions: [...document.querySelectorAll('main [data-terminal]')].map((block) => ({
          platform: block.closest('[data-platform-part]')?.dataset.platformPart,
          lines: text(block.querySelector('[data-capture="session"]')).split('\n'),
        })),
        output: [...document.querySelectorAll('main [data-capture]:not([data-capture="session"])')].map(
          (element) => ({ kind: element.dataset.capture, text: text(element) }),
        ),
        rows: [...document.querySelectorAll('main table[data-result-table] tbody tr')].map((row) => ({
          revision: text(row.children[0]).trim(),
          sum: text(row.children[2]).trim(),
        })),
        bars: [...document.querySelectorAll('main [data-bar-row]')].map((row) => ({
          revision: text(row.querySelector('.bar-revision')).trim(),
          sum: text(row.querySelector('.bar-value')).trim(),
        })),
        // The file list of the package folder, in the step that unpacks.
        packageFiles: [...document.querySelectorAll('main #unpack [data-file-list] li')].map((row) => ({
          name: text(row.querySelector('[data-file-name]')).trim(),
          platform: row.dataset.platformPart,
        })),
        sums: [...document.querySelectorAll('main [data-sha256]')].map((element) => ({
          platform: element.dataset.sha256,
          sum: text(element).trim(),
        })),
        text: document.querySelector('main').textContent,
      };
    });

    // Commands.
    expect(shown.commands.length > 0, `${name}: the page holds no command`);
    for (const block of shown.commands) {
      for (const command of block.command.split('\n')) {
        const source = sourceOf(command, block, lang);
        if (source) found[source] += 1;
        const where = block.terminal
          ? `the guide ${GUIDES[lang]} of the ${block.platform} package, with "--lang ${lang}"`
          : block.step <= 3
            ? 'the release notes or the README of the release'
            : `the guide ${GUIDES[lang]} of the ${block.platform} package or a code block of the release notes`;
        expect(Boolean(source), `${name}, step ${block.step}, ${block.platform}: the command "${command}" does not stand in ${where}`);
      }
    }

    // File names and sums.
    const names = new Set([...Object.values(archives), ...Object.values(folders)]);
    for (const [word] of shown.text.matchAll(/deltarecon-\d[\w.-]*[\w]/g)) {
      expect(names.has(word), `${name}: "${word}" is neither an archive of SHA256SUMS nor the folder of one`);
    }
    for (const platform of PLATFORMS) {
      expect(shown.text.includes(archives[platform]), `${name}: the page does not name the archive ${archives[platform]}`);
    }
    expect(shown.sums.length > 0, `${name}: the page shows no SHA-256`);
    for (const { platform, sum } of shown.sums) {
      expect(sum === sums.get(archives[platform]), `${name}: the SHA-256 of the ${platform} archive is shown as ${sum}, SHA256SUMS names ${sums.get(archives[platform])}`);
    }
    for (const [sum] of shown.text.matchAll(/\b[0-9a-fA-F]{64}\b/g)) {
      expect([...sums.values()].includes(sum), `${name}: the SHA-256 ${sum} is not in SHA256SUMS`);
    }

    // The file list of the package folder: the entries of the unpacked package.
    expect(shown.packageFiles.length > 0, `${name}: step "unpack" holds no file list of the package folder`);
    for (const platform of PLATFORMS) {
      const listed = shown.packageFiles
        .filter((file) => !file.platform || file.platform === platform)
        .map((file) => file.name)
        .sort();
      const unpacked = (await readdir(path.join(releaseFolder, folders[platform]), { withFileTypes: true }))
        .map((entry) => (entry.isDirectory() ? `${entry.name}/` : entry.name))
        .sort();
      expect(
        listed.join() === unpacked.join(),
        `${name}: the file list of the package folder names [${listed.join(', ')}] for ${platform}, ${relative(path.join(releaseFolder, folders[platform]))} holds [${unpacked.join(', ')}]`,
      );
    }

    // The terminal sessions, line by line.
    expect(shown.sessions.length === PLATFORMS.length, `${name}: not one terminal session per platform`);
    for (const session of shown.sessions) {
      const capture = captures[lang][session.platform];
      if (!capture) {
        failures.push(`${name}: a terminal session of no platform`);
        continue;
      }
      expect(session.lines.length > 5, `${name}, ${session.platform}: the terminal session has ${session.lines.length} lines`);
      session.lines.forEach((line, index) => {
        expect(
          line === capture.lines[index],
          `${name}, ${session.platform}: line ${index + 1} of the terminal session is "${line}", ${capture.file}:${index + 1} is "${capture.lines[index]}"`,
        );
      });
    }

    // Every other output stands in the capture of the language.
    const whole = squash(captures[lang].windows.lines.join(' '));
    const kinds = new Set(shown.output.map((part) => part.kind));
    for (const kind of ['after', 'caption', 'head', 'row', 'not-resolved']) {
      expect(kinds.has(kind), `${name}: the page shows no output of the kind "${kind}"`);
    }
    for (const part of shown.output) {
      expect(
        squash(part.text) !== '' && whole.includes(squash(part.text)),
        `${name}: the output "${squash(part.text)}" (${part.kind}) does not stand in ${captures[lang].windows.file}`,
      );
    }

    // Table and bar figure show the search result.
    const expected = rowsOf(lang);
    for (const [part, rows] of [
      ['result table', shown.rows],
      ['bar figure', shown.bars],
    ]) {
      expect(
        JSON.stringify(rows) === JSON.stringify(expected),
        `${name}: the ${part} shows ${JSON.stringify(rows)}, search.result.json gives ${JSON.stringify(expected)}`,
      );
    }
  }
  expect(stepPages.length === LANGUAGES.length, `the Quick start is not in the page register once per language`);
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(
  `release ${version}: the four captures agree with each other and with the search result of the pin; on the Quick start of both languages ${found['release notes']} command lines stand in the release notes, ${found.README} in the README of the release and ${found.guide} in the package guides; file names, sums and output are those of the release`,
);
