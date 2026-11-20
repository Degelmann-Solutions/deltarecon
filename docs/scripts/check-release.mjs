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
//     time stamp of the demo folder are set aside, and the one line more
//     that the Windows capture ends with, which must be the line of `pause`
//     the Windows starter prints;
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
//     message; the two terminal sessions are those of the two platforms;
//     table and bar figure show the revisions and sums of
//     `search.result.json`.
//
// The page "Your own calculations on the reference model" has captures of
// its own (src/captures/v<version>/own-calculations/, one file per step and
// platform) and its commands stand in no guide. For it the check holds,
// before the build:
//   - `order.txt` names the steps of the captures, and each has a Windows
//     and a Linux file of the shape `command: …`, output, `exit status: n`;
//     the two agree in the number of commands, in every exit status and in
//     every line of output once path separators, the time stamp of the demo
//     folder and the folder of the package are set aside; a command that
//     starts the launcher is the same on both platforms apart from the name
//     of the launcher and the separators;
// and on the built page of both languages:
//   - every command that starts the launcher names a command of the
//     released `deltarecon`, and every option it gives stands in the help of
//     that command (`deltarecon --help`, `deltarecon <command> --help` of
//     the unpacked Linux package of the release folder, which this check
//     runs, so it needs Linux on x86-64);
//   - the commands of the platform switch and of the terminal session of a
//     step are the commands of the capture of that step and platform, and
//     the session shows the output of the capture line by line, where a
//     mark of a cut stands for as many lines as it names;
//   - every other output of the page (a quoted message, a line of the
//     summary list) stands in a capture of the page; "…" in it stands for a
//     part that is left out.
//
// The page "Single commands" describes every command of the released
// `deltarecon`. For it the check holds, on the built page of both languages,
// against the same help of the unpacked Linux package:
//   - the sections marked as the section of a command (`data-command`) are
//     the commands the help names, in its order, each under the anchor of
//     its name: a command the page lacks and a section of a command the help
//     does not name both fail;
//   - in the section of a command the marked options (`data-option`) are
//     the options its help names, without `--help`: an option the page lacks,
//     an option the help does not name and an option that stands twice all
//     fail and name command and option;
//   - the last section, which describes the options several commands share,
//     marks only options that at least two commands take; in the section of
//     a command exactly these are named as shared (`data-shared`), with a
//     link to that section;
//   - an example command stands in the section of a command alone, once per
//     platform; it starts that command (`quickstart` through its starter)
//     and is a line of the guide of the page's language in the package of
//     the platform. The example of `walk`, which no guide holds, starts the
//     launcher of the platform, names only options of the help of `walk`,
//     and is the same on both platforms apart from the launcher and the
//     path separators. `compare` has no example.
// Exits non-zero and names what differs or what is missing: a file of the
// release folder, the pin, a search result of another shape, a build that
// does not start.
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
/** The line of `pause` the Windows starter ends with, as Windows prints it in English and in German. */
const PAUSE = [/^Press any key to continue \. \. \. ?$/, /^Drücken Sie eine beliebige Taste \. \. \. ?$/];
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
} else {
  for (const file of ['SHA256SUMS', 'release-notes.md']) {
    expect(
      existsSync(path.join(releaseFolder, file)),
      `${relative(path.join(releaseFolder, file))}: the file is missing in the folder of the release ${version}`,
    );
  }
}
expect(existsSync(pin), `${relative(pin)}: the pin of the search result is missing`);
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
  for (const guide of Object.values(GUIDES)) {
    if (!folders[platform]) continue;
    const file = path.join(releaseFolder, folders[platform], guide);
    expect(existsSync(file), `${relative(file)}: the guide of the ${platform} package is missing`);
  }
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
/** The revisions that deviate, with their sums, in the order of the result. */
let contributions;
let notResolved;
let counts;
try {
  const result = JSON.parse(resultText.toString('utf8'));
  contributions = result.contributions.flatMap((interval) => {
    const sum = interval.contributions.find((entry) => entry.quantity === QUANTITY && entry.contributes)?.sum;
    return sum === undefined ? [] : [{ revision: interval.revisions.at(-1).slice(0, 7), sum }];
  });
  notResolved = result.findings
    .filter((finding) => finding.code === 'interval_not_resolved')
    .map((finding) => finding.revisions.map((revision) => revision.slice(0, 7)));
  counts = [contributions.length, result.runs.search, result.runs.walk, result.runs.saved];
  if (!contributions.every(({ sum }) => typeof sum === 'number') || !counts.every(Number.isInteger)) {
    throw new Error('a sum or a count of computations is not a number');
  }
} catch (error) {
  failures.push(
    `${resultFile}: not a search result of the shape the check reads (contributions with revisions and sums, findings with revisions, runs.search, runs.walk, runs.saved): ${error.message}`,
  );
  report('');
}
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
  // of the demo: one line more than the Linux capture. Only that line is
  // set aside.
  let windowsLines = windows.lines;
  if (windows.lines.length === linux.lines.length + 1) {
    const last = windows.lines.at(-1);
    expect(
      PAUSE.some((pause) => pause.test(last)),
      `${windows.file}:${windows.lines.length}: the line the capture has more than ${linux.file} is "${last}", expected the line of \`pause\` the Windows starter ends with`,
    );
    windowsLines = windows.lines.slice(0, -1);
  }
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
// ---- The captures of the page of own calculations ----

const OWN = 'own-calculations';
const ownFolder = path.join(captureFolder, OWN);
/** The names of the launcher, per platform. */
const LAUNCHER = { windows: '.\\deltarecon.cmd', linux: './deltarecon' };

/** A line of such a capture without what varies by run and by platform. */
const neutralOwn = (line) => {
  let text = neutral(line);
  // The folder the package was unpacked into: the path up to the package folder.
  for (const platform of PLATFORMS) {
    text = text.replace(
      new RegExp(`(?:[A-Za-z]:)?/\\S*/${folders[platform].replaceAll('.', '\\.')}(?=/)`, 'g'),
      '<package folder>',
    );
  }
  return text;
};

/** The commands of a capture file: as typed, the lines printed, the exit status. */
function parseOwn(file, text) {
  const commands = [];
  let open;
  text
    .replace(/\n$/, '')
    .split('\n')
    .forEach((line, index) => {
      const status = /^exit status: (-?\d+)$/.exec(line);
      if (line.startsWith('command: ')) {
        expect(!open, `${file}:${index + 1}: a command begins before the exit status of the command before it`);
        open = { command: line.slice('command: '.length), lines: [], first: index + 2 };
      } else if (!open) {
        failures.push(`${file}:${index + 1}: the line stands before a line "command: …"`);
      } else if (status) {
        commands.push({ ...open, status: Number(status[1]) });
        open = undefined;
      } else {
        open.lines.push(line);
      }
    });
  expect(!open, `${file}: no exit status after the last command`);
  expect(commands.length > 0, `${file}: the capture holds no command`);
  return commands;
}

const own = {};
let ownSteps = [];
try {
  ownSteps = (await read(path.join(root, ownFolder, 'order.txt'))).split('\n').filter((step) => step.trim() !== '');
} catch {
  failures.push(`docs/${path.join(ownFolder, 'order.txt')}: the file that names the steps of the captures is missing`);
}
for (const step of ownSteps) {
  own[step] = {};
  for (const platform of PLATFORMS) {
    const file = path.join('docs', ownFolder, `${step}-${platform}.txt`);
    try {
      const text = await read(path.join(repository, file));
      expect(!text.includes('\r'), `${file}: the capture holds a carriage return; captures have LF line ends`);
      own[step][platform] = { file, commands: parseOwn(file, text) };
    } catch {
      failures.push(`${file}: the capture file is missing`);
    }
  }
  const { windows, linux } = own[step];
  if (!windows || !linux) continue;
  expect(
    windows.commands.length === linux.commands.length,
    `${windows.file} holds ${windows.commands.length} commands, ${linux.file} holds ${linux.commands.length}`,
  );
  windows.commands.forEach((command, index) => {
    const twin = linux.commands[index];
    if (!twin) return;
    expect(
      command.status === twin.status,
      `${windows.file} and ${linux.file}: command ${index + 1} ends with exit status ${command.status} on Windows and ${twin.status} on Linux`,
    );
    if (command.command.startsWith(`${LAUNCHER.windows} `) || twin.command.startsWith(`${LAUNCHER.linux} `)) {
      expect(
        command.command.replaceAll('\\', '/').replace('./deltarecon.cmd ', './deltarecon ') === twin.command,
        `${windows.file} and ${linux.file}: command ${index + 1} differs beyond the name of the launcher and the path separators: "${command.command}" and "${twin.command}"`,
      );
    }
    expect(
      command.lines.length === twin.lines.length,
      `${windows.file} and ${linux.file}: command ${index + 1} printed ${command.lines.length} lines on Windows and ${twin.lines.length} on Linux`,
    );
    for (let at = 0; at < Math.min(command.lines.length, twin.lines.length); at += 1) {
      expect(
        neutralOwn(command.lines[at]) === neutralOwn(twin.lines[at]),
        `${windows.file}:${command.first + at} and ${linux.file}:${twin.first + at} differ beyond path separators, the time stamp and the folder of the package: "${command.lines[at]}" and "${twin.lines[at]}"`,
      );
    }
  });
}
expect(ownSteps.length > 0, `docs/${path.join(ownFolder, 'order.txt')} names no step`);

// A capture that differs fails here, with file and line, before the build.
if (failures.length > 0) report('');

// ---- The built pages ----

const build = spawnSync('npm', ['run', 'build'], { cwd: root, encoding: 'utf8' });
if (build.error) {
  failures.push(`the build could not be started (npm run build): ${build.error.message}`);
  report('');
}
if (build.status !== 0) {
  failures.push(`the build failed:\n${build.stdout}\n${build.stderr}`);
  report('');
}

const notes = commandsOfMarkdown(await read(path.join(releaseFolder, 'release-notes.md')));
// The README of the release, which its notes point to: the file at the tag.
const tagged = spawnSync('git', ['show', `v${version}:README.md`], { cwd: repository, encoding: 'utf8' });
if (tagged.error || tagged.status !== 0) {
  failures.push(`git show v${version}:README.md failed; the check reads the README of the release: ${tagged.error?.message ?? tagged.stderr.trim()}`);
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

/** The help of the released `deltarecon`: of the program, or of one of its commands. */
function helpOf(...command) {
  const launcher = path.join(releaseFolder, folders.linux, 'deltarecon');
  const help = spawnSync(launcher, [...command, '--help'], { encoding: 'utf8' });
  if (help.error || help.status !== 0) {
    failures.push(
      `${relative(launcher)} ${[...command, '--help'].join(' ')} failed; the check reads the help of the released package, on Linux: ${help.error?.message ?? help.stderr.trim()}`,
    );
    report('');
  }
  return help.stdout;
}
/** The commands the released `deltarecon` has, and the options each takes. */
const released = new Map();
for (const command of (/\{([\w,]+)\}/.exec(helpOf())?.[1] ?? '').split(',').filter(Boolean)) {
  released.set(command, new Set([...helpOf(command).matchAll(/--[a-z][a-z-]*/g)].map(([option]) => option)));
}
expect(released.size > 0, `the help of the released deltarecon names no command`);

/** The words of a command line; a part in quotation marks is one word. */
const wordsOf = (line) => [...line.matchAll(/"[^"]*"|\S+/g)].map(([word]) => word);

const allPages = await loadPages();
const stepPages = allPages.filter((entry) => entry.id === 'quick-start');
const ownPages = allPages.filter((entry) => entry.id === OWN);
/** The page that describes every command, and what stands in no guide there. */
const SINGLE = 'single-commands';
const SHARED_SECTION = 'shared-options';
const NO_GUIDE = 'walk';
const NO_EXAMPLE = 'compare';
/** The starter of the guided demo, per platform, as the guides write it. */
const STARTER = { windows: '.\\quickstart.cmd', linux: './quickstart' };
const singlePages = allPages.filter((entry) => entry.id === SINGLE);
const { origin: reported, stop } = startPreview();
let browser;
const found = { 'release notes': 0, README: 0, guide: 0, help: 0, lines: 0 };
const single = { commands: 0, options: 0, guide: 0, help: 0 };
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
    const sessionsOf = shown.sessions.map((session) => session.platform);
    expect(
      sessionsOf.length === PLATFORMS.length && PLATFORMS.every((platform) => sessionsOf.includes(platform)),
      `${name}: not one terminal session per platform; the sessions are those of [${sessionsOf}], expected [${PLATFORMS}]`,
    );
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

  // ---- The page of own calculations ----
  const everyOwnLine = squash(
    Object.values(own)
      .flatMap((step) => Object.values(step))
      .flatMap((capture) => capture.commands.flatMap((command) => command.lines))
      .join(' '),
  );
  for (const entry of ownPages) {
    const name = entry.address;
    await page.goto(`${origin}${entry.address}`);
    const shown = await page.evaluate(() => {
      const place = (block) => ({
        step: block.closest('[data-step]')?.id,
        platform: block.closest('[data-platform-part]')?.dataset.platformPart,
      });
      return {
        steps: [...document.querySelectorAll('main [data-step]')].map((step) => step.id),
        blocks: [...document.querySelectorAll('main [data-copy]')].map((block) => ({
          ...place(block),
          terminal: block.matches('[data-terminal]'),
          commands: block.dataset.copy.split('\n'),
          typed: [...block.querySelectorAll('[data-terminal-command]')].map((command) => command.textContent),
          // What each command of a session printed: its lines, a mark of a
          // cut as the number of lines it stands for.
          outputs: [...block.querySelectorAll('[data-terminal-command]')].map((command) => {
            const output = command.nextElementSibling;
            if (!output?.matches('[data-capture="command-output"]')) return [];
            const lines = [];
            let line = '';
            for (const node of output.childNodes) {
              // The mark of a cut stands on a line of its own, in the
              // place of the lines it names; `null`: that line is taken.
              if (node.nodeType === Node.ELEMENT_NODE && node.matches('[data-cut]')) {
                lines.push({ cut: Number(node.dataset.cut) });
                line = null;
                continue;
              }
              for (const [index, part] of node.textContent.split('\n').entries()) {
                if (index > 0) {
                  if (line !== null) lines.push(line);
                  line = '';
                }
                if (line !== null) line += part;
              }
            }
            if (line !== null) lines.push(line);
            return lines;
          }),
        })),
        output: [...document.querySelectorAll('main [data-capture]:not([data-capture="command-output"])')].map(
          (element) => ({ kind: element.dataset.capture, text: element.textContent }),
        ),
      };
    });

    // Every step of the page has its captures, and every capture is shown
    // or quoted: a capture that is no step of the page is a quoted message.
    for (const step of shown.steps) {
      expect(Boolean(own[step]), `${name}: the step "${step}" has no capture in docs/${ownFolder} (order.txt)`);
    }
    expect(shown.blocks.length > 0, `${name}: the page holds no command`);
    for (const block of shown.blocks) {
      const at = `${name}, step "${block.step}", ${block.platform}`;
      const capture = own[block.step]?.[block.platform];
      if (!capture) {
        failures.push(`${at}: a command of no captured step or platform`);
        continue;
      }
      // The commands are those of the capture.
      const captured = capture.commands.map((command) => command.command);
      expect(
        block.commands.join('\n') === captured.join('\n'),
        `${at}: the ${block.terminal ? 'terminal session' : 'platform switch'} shows the command "${block.commands.join(' | ')}", ${capture.file} holds "${captured.join(' | ')}"`,
      );
      // A command that starts the launcher: its command and options are in the help.
      for (const command of block.commands) {
        const [launcher, sub, ...rest] = wordsOf(command);
        if (!/deltarecon/.test(launcher)) continue;
        expect(launcher === LAUNCHER[block.platform], `${at}: the command starts "${launcher}", expected the launcher "${LAUNCHER[block.platform]}"`);
        const options = released.get(sub);
        expect(Boolean(options), `${at}: "${sub}" is no command of the released deltarecon (${[...released.keys()].join(', ')})`);
        for (const option of rest.filter((word) => word.startsWith('--'))) {
          expect(
            Boolean(options?.has(option)),
            `${at}: the option "${option}" does not stand in the help of "deltarecon ${sub}" of the release`,
          );
          if (options?.has(option)) found.help += 1;
        }
      }
      if (!block.terminal) continue;
      // The session: every command as typed, and its output line by line.
      expect(
        block.typed.join('\n') === captured.join('\n'),
        `${at}: the terminal session types "${block.typed.join(' | ')}", ${capture.file} holds "${captured.join(' | ')}"`,
      );
      capture.commands.forEach((command, index) => {
        const lines = block.outputs[index] ?? [];
        let line = 0;
        for (const part of lines) {
          if (typeof part === 'object') {
            line += part.cut;
            continue;
          }
          expect(
            part === command.lines[line],
            `${at}: line ${line + 1} of the output of "${command.command.slice(0, 40)}…" is "${part}", ${capture.file}:${command.first + line} is "${command.lines[line]}"`,
          );
          line += 1;
        }
        expect(
          line === command.lines.length,
          `${at}: the session shows or leaves out ${line} lines of the output of "${command.command.slice(0, 40)}…", ${capture.file} holds ${command.lines.length}`,
        );
        found.lines += line;
      });
    }
    // Each step holds the commands of both platforms twice: switch and session.
    for (const step of shown.steps) {
      for (const platform of PLATFORMS) {
        const kinds = shown.blocks.filter((block) => block.step === step && block.platform === platform).map((block) => block.terminal);
        expect(
          kinds.length === 2 && kinds.includes(true) && kinds.includes(false),
          `${name}, step "${step}", ${platform}: not one platform switch and one terminal session with the commands of the step`,
        );
      }
    }
    // Every other output stands in a capture; "…" stands for a part left out.
    expect(shown.output.length > 0, `${name}: the page quotes no output beside its sessions`);
    for (const part of shown.output) {
      const pieces = squash(part.text).split('…').map((piece) => piece.trim()).filter(Boolean);
      expect(
        pieces.length > 0 && pieces.every((piece) => everyOwnLine.includes(piece)),
        `${name}: the output "${squash(part.text)}" (${part.kind}) does not stand in a capture of docs/${ownFolder}`,
      );
    }
    // A capture that is no step of the page is quoted on it.
    for (const step of ownSteps.filter((candidate) => !shown.steps.includes(candidate))) {
      const lines = own[step].linux.commands.flatMap((command) => command.lines).map(squash);
      expect(
        shown.output.some((part) => squash(part.text).split('…').every((piece) => lines.some((line) => line.includes(piece.trim())))),
        `${name}: the capture "${step}" is neither a step of the page nor quoted on it`,
      );
    }
  }
  expect(ownPages.length === LANGUAGES.length, `the page "${OWN}" is not in the page register once per language`);

  // ---- The page of single commands ----
  /** The options the help of a command names, without `--help`. */
  const optionsOf = (command) => [...released.get(command)].filter((option) => option !== '--help');
  for (const entry of singlePages) {
    const name = entry.address;
    const lang = entry.lang;
    await page.goto(`${origin}${entry.address}`);
    // The sections of the page in order, each with what it marks.
    const sections = await page.evaluate((sharedSection) => {
      const list = [];
      const parts = document.querySelectorAll(
        'main h2[data-section-heading], main [data-option], main [data-copy], main a[href]',
      );
      for (const part of parts) {
        if (part.matches('h2')) {
          list.push({ id: part.id, command: part.dataset.command, options: [], shared: [], blocks: [], links: 0 });
          continue;
        }
        const section = list.at(-1);
        if (!section) continue;
        if (part.matches('[data-option]')) {
          section.options.push(part.dataset.option);
          if (part.hasAttribute('data-shared')) section.shared.push(part.dataset.option);
        } else if (part.matches('[data-copy]')) {
          section.blocks.push({
            platform: part.closest('[data-platform-part]')?.dataset.platformPart,
            lines: part.dataset.copy.split('\n'),
          });
        } else if (part.getAttribute('href') === `#${sharedSection}` && !part.closest('h2')) {
          section.links += 1;
        }
      }
      return list;
    }, SHARED_SECTION);

    // The sections of the commands are the commands of the help, in its order.
    const marked = sections.filter((section) => section.command !== undefined);
    const names = marked.map((section) => section.command);
    for (const command of released.keys()) {
      expect(names.includes(command), `${name}: the command "${command}" of the released deltarecon is missing: no section is marked as its section`);
    }
    for (const section of marked) {
      expect(
        released.has(section.command),
        `${name}: the section "${section.id}" is marked as the section of "${section.command}", which is no command of the released deltarecon (${[...released.keys()].join(', ')})`,
      );
      expect(section.id === section.command, `${name}: the section of the command "${section.command}" has the anchor "${section.id}", expected the name of the command`);
    }
    expect(
      new Set(names).size === names.length,
      `${name}: a command has more than one section: [${names}]`,
    );
    expect(
      names.filter((command) => released.has(command)).join() === [...released.keys()].filter((command) => names.includes(command)).join(),
      `${name}: the sections of the commands stand in the order [${names}], the help names [${[...released.keys()]}]`,
    );

    // The section of the shared options: only options several commands take.
    const sharedSections = sections.filter((section) => section.command === undefined && section.options.length > 0);
    expect(
      sharedSections.length === 1 && sharedSections[0].id === SHARED_SECTION,
      `${name}: options are marked outside the sections of the commands in [${sharedSections.map((section) => section.id)}], expected the section "${SHARED_SECTION}" alone`,
    );
    const sharedOptions = sections.find((section) => section.id === SHARED_SECTION)?.options ?? [];
    expect(new Set(sharedOptions).size === sharedOptions.length, `${name}, section "${SHARED_SECTION}": an option stands twice: [${sharedOptions}]`);
    for (const option of sharedOptions) {
      const takers = [...released.keys()].filter((command) => released.get(command).has(option));
      expect(
        takers.length >= 2,
        `${name}, section "${SHARED_SECTION}": the option "${option}" is described as shared, the help names it for [${takers}]`,
      );
    }

    for (const section of marked) {
      const command = section.command;
      if (!released.has(command)) continue;
      single.commands += 1;
      const at = `${name}, command "${command}"`;
      // The options: those of the help, each once.
      const wanted = optionsOf(command);
      for (const option of wanted) {
        expect(section.options.includes(option), `${at}: the option "${option}" of the help of the released "deltarecon ${command}" is missing in its section`);
      }
      for (const option of new Set(section.options)) {
        expect(wanted.includes(option), `${at}: the option "${option}" does not stand in the help of the released "deltarecon ${command}"`);
        expect(
          section.options.filter((candidate) => candidate === option).length === 1,
          `${at}: the option "${option}" stands more than once in its section`,
        );
        if (wanted.includes(option)) single.options += 1;
      }
      // Its shared options: named as such, with a link to their section.
      const expectedShared = wanted.filter((option) => sharedOptions.includes(option));
      expect(
        [...section.shared].sort().join() === [...expectedShared].sort().join(),
        `${at}: the options named as shared are [${section.shared}], the section "${SHARED_SECTION}" describes [${expectedShared}] of its options`,
      );
      expect(
        expectedShared.length === 0 || section.links > 0,
        `${at}: its section names shared options and holds no link to the section "${SHARED_SECTION}"`,
      );

      // The example command.
      if (command === NO_EXAMPLE) {
        expect(section.blocks.length === 0, `${at}: its section holds an example command; a compare request is written by other commands`);
        continue;
      }
      const lines = {};
      for (const platform of PLATFORMS) {
        const blocks = section.blocks.filter((block) => block.platform === platform);
        expect(
          blocks.length === 1 && blocks[0].lines.length === 1,
          `${at}, ${platform}: not one example command of one line (${blocks.map((block) => block.lines.length)} lines per block)`,
        );
        const line = blocks[0]?.lines[0];
        if (!line) continue;
        lines[platform] = line;
        const [launcher, sub, ...rest] = wordsOf(line);
        // It starts the command of its section.
        expect(
          command === 'quickstart' ? launcher === STARTER[platform] : launcher === LAUNCHER[platform] && sub === command,
          `${at}, ${platform}: the example "${line}" does not start "${command}" through "${command === 'quickstart' ? STARTER[platform] : LAUNCHER[platform]}"`,
        );
        if (guides[lang][platform].has(line)) {
          single.guide += 1;
          continue;
        }
        if (command !== NO_GUIDE) {
          failures.push(`${at}, ${platform}: the example "${line}" does not stand in the guide ${GUIDES[lang]} of the ${platform} package`);
          continue;
        }
        // No guide holds it: every option stands in the help of the command.
        const options = rest.filter((word) => word.startsWith('--'));
        for (const option of options) {
          expect(released.get(command).has(option), `${at}, ${platform}: the option "${option}" of the example does not stand in the help of the released "deltarecon ${command}"`);
        }
        if (options.every((option) => released.get(command).has(option))) single.help += 1;
      }
      if (command === NO_GUIDE && lines.windows && lines.linux) {
        expect(
          lines.windows.replaceAll('\\', '/').replace('./deltarecon.cmd ', './deltarecon ') === lines.linux,
          `${at}: the example differs between the platforms beyond the name of the launcher and the path separators: "${lines.windows}" and "${lines.linux}"`,
        );
      }
    }
    // No example outside the section of a command.
    for (const section of sections.filter((candidate) => candidate.command === undefined)) {
      expect(section.blocks.length === 0, `${name}, section "${section.id}": a command stands outside the section of a command`);
    }
  }
  expect(singlePages.length === LANGUAGES.length, `the page "${SINGLE}" is not in the page register once per language`);
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(
  `release ${version}: the four captures agree with each other and with the search result of the pin; on the Quick start of both languages ${found['release notes']} command lines stand in the release notes, ${found.README} in the README of the release and ${found.guide} in the package guides; file names, sums and output are those of the release; on the page of own calculations of both languages the commands are those of the ${ownSteps.length} captured steps, ${found.help} options stand in the help of the released deltarecon and ${found.lines} lines of output are those of the captures; on the page of single commands of both languages the ${single.commands} sections of commands are the ${released.size} commands of the released deltarecon in each language, ${single.options} options stand in the help of their command and no command and no option of the package is missing, ${single.guide} example commands stand in the package guides and ${single.help} use options of the help alone`,
);
