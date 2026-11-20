// Holds what the built pages show of the repository's code against the tag
// of the release the documentation applies to (src/release.json). Run after
// the build: `npm run check`.
//
// It reads Git with the `git` program and needs, in the local clone, the tag
// `v<release>` and the branch `main`.
//
// On every page of the register, in both languages:
//   - a code excerpt (CodeExcerpt.astro): the code is, character for
//     character, the lines its head row names of its file at the tag
//     (`git show v<release>:<file>`); the head row names the file, the lines
//     and the tag;
//   - the signature of a member card (Member.astro): its code is, line for
//     line, the lines it names of its file at the tag, without the
//     indentation those lines share;
//   - a row or a member card marked as a member of the protocol (Row with
//     `member`, Member with `of`): the name
//     is a member of that class in degelmann/deltarecon/protocol.py at the
//     tag, a method or an annotated attribute; a row with a tag (as
//     "optional") may instead name an operation that the comment of the class
//     describes. A row marked as a name of the engine selection (Row with
//     `selection`): the first word of its code name stands in
//     degelmann/deltarecon/engine_selection.py at the tag. On a page that
//     holds such rows, every code name of a row carries one of the two marks;
//   - a page named as complete (`COMPLETE`, the page that walks through the
//     protocol): every member of `Engine` and of `Session` at the tag, the
//     operations their comments describe included, has exactly one row
//     marked as that member;
//   - a number of lines (`data-lines-of`) and the yardstick box
//     (YardstickBox.astro): the number is that of the file at the tag, for
//     the box the sum over its files, each of which the box names as inline
//     code.
// And once: the two files are the same on `main` as at the tag, so that the
// pages describe the protocol as it is.
//
// First it proves itself on texts it sets itself: an altered excerpt, a
// range that does not hold the code, a member the protocol does not hold, a
// member a complete page leaves out or names twice, a file that differs on
// `main`, a wrong number of lines and a tag the clone does not hold must each
// fail and name what the message is to name.
//
// Exits non-zero and names page and part of every failed expectation.
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { chromium } from 'playwright';
import { expectations, loadPages, loadRelease, root, startPreview } from './harness.mjs';

const PROTOCOL = 'degelmann/deltarecon/protocol.py';
const SELECTION = 'degelmann/deltarecon/engine_selection.py';
const MAIN = 'main';
/** The classes of the protocol an engine implements. */
const CLASSES = ['Engine', 'Session'];
/**
 * The pages, by their id in the register, that walk through the protocol:
 * each names every member of the classes above exactly once.
 */
const COMPLETE = ['build-an-adapter'];
const repository = path.resolve(root, '..');

const { failures, expect, report } = expectations('check-excerpts');

/** The output of a Git command, or `null` when it fails. */
function git(...args) {
  try {
    return execFileSync('git', ['-C', repository, ...args], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    return null;
  }
}

/** The lines of a text; a line break at the end opens no further line. */
function linesOf(text) {
  const lines = text.split('\n');
  if (lines.at(-1) === '') lines.pop();
  return lines;
}

/** The digits of a number as a page writes it: "1,170" and "1.170" are 1170. */
function numberOf(shown) {
  return /^\d{1,3}([.,]\d{3})*$|^\d+$/.test(shown) ? Number(shown.replace(/[.,]/g, '')) : Number.NaN;
}

/** Why the tag cannot be read, or `null`. `holds(ref)` says whether the clone holds a reference. */
function tagFault(tag, holds) {
  return holds(`refs/tags/${tag}`)
    ? null
    : `the tag ${tag} of the release (src/release.json) is not a tag of the local repository; fetch it (git fetch --tags)`;
}

/**
 * What is wrong with the signature of a member card: its code is, line for
 * line, the lines it names of its file at the tag, without the indentation
 * those lines share.
 */
function signatureFaults(found, tag, source) {
  const which = `signature "${found.key}" (${found.file}, lines ${found.first} to ${found.last})`;
  const lines = source(found.file);
  if (!lines) return [`${which}: ${tag} holds no file ${found.file}`];
  if (!(Number.isInteger(found.first) && Number.isInteger(found.last) && found.first >= 1 && found.last >= found.first && found.last <= lines.length)) {
    return [`${which}: these are no lines of the file at ${tag}`];
  }
  const named = lines.slice(found.first - 1, found.last);
  const shared = Math.min(...named.filter((line) => line.trim() !== '').map((line) => line.length - line.trimStart().length));
  const expected = named.map((line) => line.slice(shared)).join('\n');
  if (found.code !== expected) {
    return [`${which}: the file holds ${JSON.stringify(expected)} at ${tag}, the page shows ${JSON.stringify(found.code)}`];
  }
  // The lines are the signature of the member the key names, and all of it.
  const name = found.key.includes('.') ? found.key.split('.').pop() : '__init__';
  const faults = [];
  if (!new RegExp(`^(def ${name}\\(|${name}:)`).test(expected)) faults.push(`${which}: these lines are not the signature of "${name}"`);
  if (expected.startsWith('def ') && !/:\s*(#.*)?$/.test(expected)) faults.push(`${which}: the signature does not end in these lines`);
  return faults;
}

/**
 * What is wrong with a code excerpt of a page. `source` gives the lines of a
 * file at the tag, or `null` for a file the tag does not hold.
 */
function excerptFaults(found, tag, source) {
  const faults = [];
  const which = `excerpt of ${found.file}, lines ${found.first} to ${found.last}`;
  if (found.release !== tag) faults.push(`${which}: it names the release "${found.release}", not ${tag}`);
  for (const part of [found.file, tag, String(found.first), String(found.last)]) {
    const escaped = part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!new RegExp(`(^|[^\\w.])${escaped}($|[^\\w.])`).test(found.head)) {
      faults.push(`${which}: its head row "${found.head}" does not name "${part}"`);
    }
  }
  const lines = source(found.file);
  if (!lines) {
    faults.push(`${which}: ${tag} holds no file ${found.file}`);
    return faults;
  }
  if (!(Number.isInteger(found.first) && Number.isInteger(found.last) && found.first >= 1 && found.last >= found.first)) {
    faults.push(`${which}: these are no lines`);
    return faults;
  }
  if (found.last > lines.length) {
    faults.push(`${which}: the file has ${lines.length} lines at ${tag}`);
    return faults;
  }
  const shown = found.code.split('\n');
  const named = lines.slice(found.first - 1, found.last);
  if (shown.length !== named.length) {
    faults.push(`${which}: the page shows ${shown.length} lines, the range holds ${named.length}`);
  }
  for (let index = 0; index < Math.min(shown.length, named.length); index += 1) {
    if (shown[index] !== named[index]) {
      faults.push(
        `${which}: line ${found.first + index} of ${found.file} at ${tag} is ${JSON.stringify(named[index])}, the page shows ${JSON.stringify(shown[index])}`,
      );
      break;
    }
  }
  return faults;
}

/**
 * The members of a class of the protocol file: those it declares (a method,
 * an annotated attribute) and the operations that a comment of the class
 * describes without declaring them. `null` for a class the file does not hold.
 */
function classMembers(lines, name) {
  const start = lines.findIndex((line) => new RegExp(`^class ${name}\\b.*:\\s*$`).test(line));
  if (start === -1) return null;
  const declared = new Set();
  const comment = [];
  let inText = false;
  for (const line of lines.slice(start + 1)) {
    if (/^\S/.test(line)) break;
    const quotes = line.split('"""').length - 1;
    if (inText) {
      if (quotes % 2 === 1) inText = false;
      continue;
    }
    if (quotes % 2 === 1) {
      inText = true;
      continue;
    }
    if (quotes > 0) continue;
    const member = /^ {4}(?:def (\w+)\(|(\w+)\s*:)/.exec(line);
    if (member) declared.add(member[1] ?? member[2]);
    else if (/^ {4}#/.test(line)) comment.push(line.replace(/^ {4}#\s?/, ''));
  }
  const described = new Set([...comment.join(' ').matchAll(/``(\w+)\(/g)].map((match) => match[1]));
  return { declared, described };
}

/** What is wrong with a row marked as a member of the protocol. */
function memberFaults(found, tag, protocol) {
  const [className, name] = found.member.split('.');
  const which = `the row of "${found.shown}"`;
  if (name !== found.shown) return [`${which} is marked as the member ${found.member}`];
  const members = classMembers(protocol, className);
  if (!members) return [`${which}: ${PROTOCOL} holds no class ${className} at ${tag}`];
  if (members.declared.has(name)) return [];
  if (members.described.has(name)) {
    return found.tagged
      ? []
      : [`${which}: ${className} does not declare ${name} in ${PROTOCOL} at ${tag}, its comment describes it as an operation a class may offer; the row carries no tag that says so`];
  }
  return [`${which}: ${name} is no member of ${className} in ${PROTOCOL} at ${tag}`];
}

/**
 * What a page that walks through the protocol leaves out or names twice.
 * `members` are its rows marked as members, as `Class.name`.
 */
function completenessFaults(members, tag, protocol) {
  const faults = [];
  for (const className of CLASSES) {
    const held = classMembers(protocol, className);
    if (!held) {
      faults.push(`${PROTOCOL} holds no class ${className} at ${tag}`);
      continue;
    }
    for (const name of [...held.declared, ...held.described]) {
      const rows = members.filter((member) => member === `${className}.${name}`).length;
      if (rows === 0) {
        faults.push(`no row names ${className}.${name}, a member of the protocol in ${PROTOCOL} at ${tag}; the page is to name every member`);
      } else if (rows > 1) {
        faults.push(`${rows} rows name ${className}.${name}; the page is to name every member of the protocol once`);
      }
    }
  }
  return faults;
}

/** What is wrong with a row marked as a name of the engine selection. */
function selectionFaults(shown, tag, selection) {
  const [name] = shown.split(/\s+/);
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^\\w-])${escaped}($|[^\\w-])`).test(selection.join('\n'))
    ? []
    : [`the row of "${shown}": ${SELECTION} does not name ${name} at ${tag}`];
}

/** What is wrong with a number of lines a page states of a file. */
function countFaults(found, tag, source) {
  const lines = source(found.file);
  if (!lines) return [`number of lines of ${found.file}: ${tag} holds no such file`];
  return numberOf(found.shown) === lines.length
    ? []
    : [`number of lines of ${found.file}: the page says "${found.shown}", the file has ${lines.length} lines at ${tag}`];
}

/** What is wrong with a yardstick box. */
function yardstickFaults(found, tag, source) {
  const faults = [];
  let sum = 0;
  for (const file of found.files) {
    const lines = source(file);
    if (!lines) {
      faults.push(`yardstick box: ${tag} holds no file ${file}`);
      continue;
    }
    sum += lines.length;
    if (!found.named.includes(file)) faults.push(`yardstick box: its text does not name ${file} as inline code`);
  }
  if (faults.length === 0 && numberOf(found.shown) !== sum) {
    faults.push(
      `yardstick box: the page says "${found.shown}" lines, ${found.files.join(' and ')} ${found.files.length === 1 ? 'has' : 'have'} ${sum} lines at ${tag}`,
    );
  }
  return faults;
}

/** The files that differ between the tag and a branch. `blob(ref, file)` names the content of a file at a reference. */
function branchFaults(tag, branch, files, blob) {
  return files.flatMap((file) => {
    const released = blob(tag, file);
    const present = blob(branch, file);
    if (!released) return [`${file}: ${tag} holds no such file`];
    if (!present) return [`${file}: the branch ${branch} is not in the local repository, or holds no such file`];
    return released === present
      ? []
      : [`${file} differs between ${tag} and ${branch} (git diff ${tag} ${branch} -- ${file}): the pages describe the file of the release`];
  });
}

/** The check on texts it sets itself: each case must fail, or pass, as named. */
function proveItself() {
  const tag = 'v9.9.9';
  const file = 'pkg/engine.py';
  const text = ['class Session(Protocol):', '    """One state."""', '', '    time_basis: str', '', '    def project(self, model_point_id: str) -> list:', '        """The periods.', '', '        raises: nothing', '        """', '', '    # A session may also offer ``project_many(model_point_ids)``: the outcome', '    # of each id.', '', '', 'class Engine(Protocol):', '    stages: Mapping[str, str]', '', '    def open(self, stage: str,', '             release: dict) -> None:', '        """Open it."""'];
  const source = (name) => (name === file ? text : null);
  const excerpt = { file, first: 4, last: 6, release: tag, head: `${file} lines 4 to 6 · ${tag}`, code: text.slice(3, 6).join('\n') };
  const member = (name, tagged = false) => ({ member: name, shown: name.split('.')[1], tagged });
  const cases = [
    ['an excerpt as the file holds it', excerptFaults(excerpt, tag, source), null],
    ['an excerpt with one character altered', excerptFaults({ ...excerpt, code: excerpt.code.replace('-> list', '-> List') }, tag, source), [file, 'line 6']],
    ['an excerpt whose head row names other lines', excerptFaults({ ...excerpt, first: 5, last: 7, head: `${file} lines 5 to 7 · ${tag}` }, tag, source), [file, 'line 5']],
    ['an excerpt with a line less than its range', excerptFaults({ ...excerpt, code: text.slice(3, 5).join('\n') }, tag, source), ['shows 2 lines']],
    ['an excerpt beyond the end of its file', excerptFaults({ ...excerpt, first: 20, last: 40, head: `${file} lines 20 to 40 · ${tag}` }, tag, source), [`has ${text.length} lines`]],
    ['an excerpt of a file the tag does not hold', excerptFaults({ ...excerpt, file: 'pkg/gone.py', head: `pkg/gone.py lines 4 to 6 · ${tag}` }, tag, source), ['pkg/gone.py']],
    ['an excerpt of another release', excerptFaults({ ...excerpt, release: 'v9.9.8' }, tag, source), ['v9.9.8']],
    ['an excerpt whose head row leaves out its lines', excerptFaults({ ...excerpt, head: `${file} · ${tag}` }, tag, source), ['head row']],
    ['a method of the protocol', memberFaults(member('Session.project'), tag, text), null],
    ['an annotated attribute of the protocol', memberFaults(member('Session.time_basis'), tag, text), null],
    ['a method whose signature spans lines', memberFaults(member('Engine.open'), tag, text), null],
    ['a name that is no member of the protocol', memberFaults(member('Session.project_all'), tag, text), ['project_all', 'no member']],
    ['a member of the other class', memberFaults(member('Engine.project'), tag, text), ['project', 'Engine']],
    ['a word of a docstring', memberFaults(member('Session.raises'), tag, text), ['raises', 'no member']],
    ['a class the protocol does not hold', memberFaults(member('Adapter.open'), tag, text), ['no class Adapter']],
    ['an operation the comment describes, on a row with a tag', memberFaults(member('Session.project_many', true), tag, text), null],
    ['an operation the comment describes, on a row without a tag', memberFaults(member('Session.project_many'), tag, text), ['project_many', 'no tag']],
    ['a page that names every member once', completenessFaults(['Session.time_basis', 'Session.project', 'Session.project_many', 'Engine.stages', 'Engine.open'], tag, text), null],
    ['a page that leaves a member out', completenessFaults(['Session.time_basis', 'Session.project', 'Session.project_many', 'Engine.stages'], tag, text), ['Engine.open', 'no row']],
    ['a page that leaves out an operation the comment describes', completenessFaults(['Session.time_basis', 'Session.project', 'Engine.stages', 'Engine.open'], tag, text), ['Session.project_many', 'no row']],
    ['a page that names a member twice', completenessFaults(['Session.time_basis', 'Session.project', 'Session.project', 'Session.project_many', 'Engine.stages', 'Engine.open'], tag, text), ['2 rows', 'Session.project;']],
    ['a name of the engine selection', selectionFaults('--engine <module>:<class>', tag, ['# ``--engine <module>:<class>``, else']), null],
    ['a name the engine selection does not hold', selectionFaults('--engine', tag, ['# ``--engine-path`` names a folder']), ['--engine']],
    ['the number of lines of a file', countFaults({ file, shown: String(text.length) }, tag, source), null],
    ['a wrong number of lines', countFaults({ file, shown: '1,170' }, tag, source), ['"1,170"', `${text.length} lines`]],
    ['a yardstick box with the number of its file', yardstickFaults({ files: [file], shown: String(text.length), named: [file] }, tag, source), null],
    ['a yardstick box with a wrong number', yardstickFaults({ files: [file], shown: '1.170', named: [file] }, tag, source), ['"1.170"', `${text.length} lines`]],
    ['a yardstick box that does not name its file', yardstickFaults({ files: [file], shown: String(text.length), named: [] }, tag, source), [file, 'inline code']],
    ['a file that is the same on the branch', branchFaults(tag, MAIN, [file], () => 'a1'), null],
    ['a file that differs on the branch', branchFaults(tag, MAIN, [file], (ref) => (ref === tag ? 'a1' : 'b2')), [file, 'differs', MAIN]],
    ['a branch the clone does not hold', branchFaults(tag, MAIN, [file], (ref) => (ref === tag ? 'a1' : null)), [file, MAIN]],
    ['a tag the clone holds', [tagFault(tag, () => true)].filter(Boolean), null],
    ['a tag the clone does not hold', [tagFault(tag, () => false)].filter(Boolean), [tag]],
  ];
  for (const [name, faults, parts] of cases) {
    if (parts === null) {
      expect(faults.length === 0, `the check on its own texts: ${name} fails: ${faults.join('; ')}`);
    } else {
      expect(
        faults.length > 0 && parts.every((part) => faults.join('; ').includes(part)),
        `the check on its own texts: ${name} ${faults.length === 0 ? 'passes' : `fails with "${faults.join('; ')}"`}, expected a failure that names ${parts.map((part) => `"${part}"`).join(' and ')}`,
      );
    }
  }
  expect(numberOf('1,170') === 1170 && numberOf('1.170') === 1170 && numberOf('281') === 281 && Number.isNaN(numberOf('1 170')) && Number.isNaN(numberOf('')), 'the check on its own texts: a number is not read as written');
  return cases.length;
}

/** What a page shows of the repository's code. */
function readPage(page) {
  return page.evaluate(() => {
    const text = (element) => element?.textContent ?? '';
    const marked = (code) => code.hasAttribute('data-member') || code.hasAttribute('data-selection');
    return {
      excerpts: [...document.querySelectorAll('main [data-code-excerpt]')].map((figure) => ({
        file: figure.dataset.file ?? '',
        first: Number(figure.dataset.first),
        last: Number(figure.dataset.last),
        release: figure.dataset.release ?? '',
        head: text(figure.querySelector('[data-code-excerpt-head]')).replace(/\s+/g, ' ').trim(),
        code: text(figure.querySelector('pre code')),
      })),
      signatures: [...document.querySelectorAll('main [data-signature]')].map((block) => ({
        key: block.dataset.signature,
        file: block.dataset.file ?? '',
        first: Number(block.dataset.first),
        last: Number(block.dataset.last),
        code: text(block.querySelector('code')),
      })),
      members: [...document.querySelectorAll('main [data-member]')].map((code) => ({
        member: code.dataset.member,
        shown: text(code).trim(),
        tagged: Boolean(
          code.closest('[data-row]')?.querySelector('[data-row-tag]') ??
            code.closest('.member-title')?.querySelector('[data-member-tag]'),
        ),
      })),
      selections: [...document.querySelectorAll('main [data-selection]')].map((code) => text(code).trim()),
      unmarked: [...document.querySelectorAll('main [data-row] .row-name code')].filter((code) => !marked(code)).map((code) => text(code).trim()),
      counts: [...document.querySelectorAll('main [data-lines-of]')].map((element) => ({
        file: element.dataset.linesOf,
        shown: text(element).trim(),
      })),
      yardsticks: [...document.querySelectorAll('main [data-yardstick]')].map((box) => ({
        files: (box.dataset.yardstickFiles ?? '').split(' ').filter(Boolean),
        shown: text(box.querySelector('[data-yardstick-lines]')).trim(),
        named: [...box.querySelectorAll('code')].map((code) => text(code).trim()),
      })),
    };
  });
}

const proved = proveItself();
const release = await loadRelease();
const tag = `v${release}`;
const totals = { pages: 0, excerpts: 0, signatures: 0, members: 0, selections: 0, counts: 0, yardsticks: 0, complete: 0 };

const missing = tagFault(tag, (ref) => git('rev-parse', '--quiet', '--verify', `${ref}^{commit}`) !== null);
if (missing) {
  failures.push(missing);
} else {
  // The files at the tag, each read once.
  const read = new Map();
  const source = (file) => {
    if (!read.has(file)) {
      const text = /^[\w./-]+$/.test(file) ? git('show', `${tag}:${file}`) : null;
      read.set(file, text === null ? null : linesOf(text));
    }
    return read.get(file);
  };
  const protocol = source(PROTOCOL);
  const selection = source(SELECTION);
  expect(protocol !== null, `${tag} holds no file ${PROTOCOL}`);
  expect(selection !== null, `${tag} holds no file ${SELECTION}`);

  // The protocol and the engine selection on `main` are those of the release.
  failures.push(...branchFaults(tag, MAIN, [PROTOCOL, SELECTION], (ref, file) => git('rev-parse', '--quiet', '--verify', `${ref}:${file}`)?.trim() || null));

  const pages = await loadPages();
  const { origin: reported, stop } = startPreview();
  let browser;
  try {
    const origin = await reported;
    browser = await chromium.launch();
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    for (const entry of pages) {
      await page.goto(`${origin}${entry.address}`);
      const found = await readPage(page);
      const faults = [
        ...found.excerpts.flatMap((excerpt) => excerptFaults(excerpt, tag, source)),
        ...found.signatures.flatMap((signature) => signatureFaults(signature, tag, source)),
        ...(protocol ? found.members.flatMap((member) => memberFaults(member, tag, protocol)) : []),
        ...(selection ? found.selections.flatMap((shown) => selectionFaults(shown, tag, selection)) : []),
        ...found.counts.flatMap((count) => countFaults(count, tag, source)),
        ...found.yardsticks.flatMap((box) => yardstickFaults(box, tag, source)),
      ];
      // On a page that names members of the protocol, a code name of a row
      // without a mark is a name no file is asked for.
      if (found.members.length + found.selections.length > 0) {
        for (const name of found.unmarked) {
          faults.push(`the row of "${name}" is marked neither as a member of the protocol nor as a name of the engine selection (Row with "member" or "selection")`);
        }
      }
      if (protocol && COMPLETE.includes(entry.id)) {
        faults.push(...completenessFaults(found.members.map((member) => member.member), tag, protocol));
        totals.complete += 1;
      }
      failures.push(...faults.map((fault) => `${entry.address}: ${fault}`));
      const held = found.excerpts.length + found.signatures.length + found.members.length + found.selections.length + found.counts.length + found.yardsticks.length;
      if (held > 0) totals.pages += 1;
      for (const part of ['excerpts', 'signatures', 'members', 'selections', 'counts', 'yardsticks']) totals[part] += found[part].length;
    }
    await context.close();
  } catch (error) {
    failures.push(error.stack ?? error.message);
  } finally {
    await browser?.close();
    stop();
  }
  // A page named as complete that the register does not hold is not checked.
  for (const id of COMPLETE) {
    expect(pages.some((entry) => entry.id === id), `the page "${id}", named as complete (COMPLETE), is no page of the register`);
  }
  // A check that finds nothing to hold proves nothing.
  expect(
    totals.excerpts > 0 && totals.members > 0 && totals.yardsticks > 0,
    `the built pages hold ${totals.excerpts} excerpts, ${totals.members} rows of members of the protocol and ${totals.yardsticks} yardstick boxes; the check expects each on at least one page`,
  );
}

report(
  `${proved} cases on its own texts; at ${tag}: ${totals.excerpts} excerpts, ${totals.signatures} signatures, ${totals.members} members of the protocol, ${totals.selections} names of the engine selection, ${totals.counts} numbers of lines and ${totals.yardsticks} yardstick boxes on ${totals.pages} pages; ${totals.complete} pages name every member of ${CLASSES.join(' and ')} once; ${PROTOCOL} and ${SELECTION} are the same on ${MAIN}`,
);
