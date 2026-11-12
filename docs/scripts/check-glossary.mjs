// Checks the Glossary and the glossary links of the built site in Chromium.
// Run after the build: `npm run check`.
//
// First it proves itself on pages it sets itself: an unlinked term, a term
// linked after its first occurrence, a term linked twice (also once in a
// heading and once in the text), a link to an unknown entry or to the wrong
// Glossary, and words that are not the term (in an exempt passage, in code,
// in a heading, in another link, inside a longer word); and on a page of the
// built site, with its stylesheet, into which it puts a glossary link with
// and without the looks of one. Each must fail or pass as expected, or the
// check fails.
//
// Then it asserts:
//   - the glossary register (src/glossary.ts): every entry has a term and an
//     explanation in both languages, and an anchor of its own;
//   - the Glossary of each language, with JavaScript on and off: the letter
//     index names the letters that have entries and leads to their labels;
//     the entries stand in the alphabetical order of the language under
//     their letters, as a description list, each with its term, the
//     counterpart with language code and `lang`, and the explanation; the two
//     Glossaries hold the same entries;
//   - every entry address: that entry, and no other, shows the linked state
//     (ground, bar, tag); the state ends when the address changes;
//   - every other page: the first occurrence of a term or one of its forms
//     in the content is the glossary link of its entry; no entry is linked
//     twice; a glossary link leads to its entry on the Glossary of the
//     page's language and has the dotted underline;
//   - "Appears in" of each entry lists exactly the pages that link the term,
//     in path order, and is absent where no page does.
//   - the way back: after a click on a glossary link of a page the entry
//     holds the link "Back to the previous page", and a click on it returns
//     to that page; the link is there again after going forward to the
//     entry and goes when the address changes; opened directly, or with a
//     Glossary of either language, another site or an address outside the
//     documentation as the page before, the entry holds none;
//
// What counts as content: the text of `main` after the page head, without
// the page links, headings, `code`, `pre`, other links, and passages marked
// `data-no-term`. Content that is not shown counts like content that is:
// with JavaScript off it may be visible. A match is a whole word; English
// matches without regard to case, German matches the case as written.
// Exits non-zero and names page and term of every failed expectation.
import { chromium } from 'playwright';
import { expectations, loadGlossary, loadPages, startPreview } from './harness.mjs';

// Private-use characters that stand in the text read from a page: before and
// after the number of a glossary link, and where a block or a part that does
// not count begins or ends.
const LINK_START = '';
const LINK_END = '';
const BREAK = '';
// The linked state: ground bg-subtle, bar teal-text.
const GROUND = 'rgb(245, 247, 250)';
const BAR = 'rgb(23, 121, 130)';
const NONE = 'rgba(0, 0, 0, 0)';
// The link back to the page a reader came from, written out per language.
const backTexts = { en: 'Back to the previous page', de: 'Zurück zur vorherigen Seite' };

const glossary = await loadGlossary();
const pages = await loadPages();
const { failures, expect, report } = expectations('check-glossary');

const isGlossary = (entry) => entry.id === glossary.glossaryPage;
/** Address of the Glossary of each language. */
const glossaryAddress = Object.fromEntries(
  pages.filter(isGlossary).map((entry) => [entry.lang, entry.address]),
);

/** Finds the term of an entry or one of its forms as a whole word. */
function matcher(entry, lang) {
  const words = [entry[lang].term, ...entry[lang].forms]
    .sort((a, b) => b.length - a.length)
    .map((word) =>
      word
        .trim()
        .split(/\s+/)
        .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('\\s+'),
    );
  return new RegExp(
    `(?<![\\p{L}\\p{N}])(?:${words.join('|')})(?![\\p{L}\\p{N}])`,
    lang === 'en' ? 'iu' : 'u',
  );
}

/**
 * Reads the open page: the text of its content with a mark in place of each
 * glossary link, those links, and every glossary link of `main`.
 */
function readContent(page) {
  return page.evaluate(
    ({ LINK_START, LINK_END, BREAK }) => {
      const main = document.querySelector('main');
      if (!main) return null;
      // The last five hold no text a reader reads as content: code of the
      // page, and the name and description of a drawing.
      const skipped =
        '[data-page-head], [data-page-links], h1, h2, h3, h4, h5, h6, code, pre, [data-no-term], a:not([data-term]), script, style, noscript, template, svg title, svg desc';
      const describe = (link) => {
        const style = getComputedStyle(link);
        return {
          anchor: link.dataset.term,
          href: link.getAttribute('href'),
          text: link.textContent.trim().replace(/\s+/g, ' '),
          underline: `${style.textDecorationLine} ${style.textDecorationStyle}`,
          colour: style.color,
          around: link.parentElement ? getComputedStyle(link.parentElement).color : style.color,
        };
      };
      const counted = [];
      const read = (node) => {
        if (node.nodeType === Node.TEXT_NODE) return node.data;
        if (node.nodeType !== Node.ELEMENT_NODE) return '';
        if (node.matches('a[data-term]')) {
          counted.push(describe(node));
          return `${LINK_START}${counted.length - 1}${LINK_END}`;
        }
        if (node.matches(skipped)) return BREAK;
        // Hidden content counts too; it is a block of its own.
        const display = getComputedStyle(node).display;
        const inner = [...node.childNodes].map(read).join('');
        return display.startsWith('inline') ? inner : `${BREAK}${inner}${BREAK}`;
      };
      const text = [...main.childNodes].map(read).join('');
      return { text, counted, all: [...main.querySelectorAll('a[data-term]')].map(describe) };
    },
    { LINK_START, LINK_END, BREAK },
  );
}

/**
 * What is wrong with the glossary links of a page, as a list of problems,
 * each with its kind, the entry and a sentence. `looks` also asserts the
 * underline, which needs the stylesheet of the site.
 */
function inspect(content, lang, { looks = true } = {}) {
  const problems = [];
  const problem = (kind, anchor, message) => problems.push({ kind, anchor, message });
  if (!content) {
    problem('page', '', 'the page has no main');
    return problems;
  }
  const termOf = (anchor) => glossary.findEntry(anchor)?.[lang].term ?? anchor;

  // Every glossary link: a known entry, its address, its looks; none twice.
  const count = new Map();
  for (const link of content.all) {
    count.set(link.anchor, (count.get(link.anchor) ?? 0) + 1);
    const entry = glossary.findEntry(link.anchor);
    if (!entry) {
      problem('unknown', link.anchor, `the glossary link "${link.text}" names the entry "${link.anchor}", which the glossary register does not hold`);
      continue;
    }
    const address = `${glossaryAddress[lang]}#${entry.anchor}`;
    if (link.href !== address) {
      problem('address', link.anchor, `the glossary link of the term "${termOf(link.anchor)}" leads to ${link.href}, expected ${address}`);
    }
    if (looks && (link.underline !== 'underline dotted' || link.colour !== link.around)) {
      problem('looks', link.anchor, `the glossary link of the term "${termOf(link.anchor)}" has not the dotted underline and the colour of its surroundings (${link.underline}, ${link.colour} in ${link.around})`);
    }
  }
  for (const [anchor, times] of count) {
    if (times > 1) {
      problem('twice', anchor, `the term "${termOf(anchor)}" is linked ${times} times; only its first occurrence is a link`);
    }
  }

  // The text without the links, and where each link stands in it.
  let plain = '';
  const position = new Map();
  const texts = [];
  const mark = new RegExp(`${LINK_START}(\\d+)${LINK_END}`, 'g');
  let last = 0;
  for (const match of content.text.matchAll(mark)) {
    plain += content.text.slice(last, match.index);
    const link = content.counted[Number(match[1])];
    if (!position.has(link.anchor)) position.set(link.anchor, plain.length);
    texts.push({ at: plain.length, text: link.text });
    plain += BREAK;
    last = match.index + match[0].length;
  }
  plain += content.text.slice(last);

  // The first occurrence of each term is its glossary link.
  for (const entry of glossary.entries) {
    const found = matcher(entry, lang).exec(plain);
    if (!found) continue;
    const linkAt = position.get(entry.anchor);
    if (linkAt !== undefined && linkAt < found.index) continue;
    // The text around it, with the words of the links back in their places.
    const from = Math.max(0, found.index - 50);
    let around = plain.slice(from, found.index + found[0].length + 50);
    for (const { at, text } of texts.filter((link) => link.at >= from).reverse()) {
      if (at - from < around.length) {
        around = `${around.slice(0, at - from)}${text}${around.slice(at - from + 1)}`;
      }
    }
    around = around
      .replaceAll(BREAK, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    problem('unlinked', entry.anchor, `the first occurrence of the term "${entry[lang].term}" is not a glossary link: "… ${around} …"`);
  }
  return problems;
}

/** What is wrong with the register itself: an entry without its counterpart. */
function inspectRegister(entries) {
  const problems = [];
  const seen = new Set();
  for (const entry of entries) {
    const name = entry.anchor || entry.en?.term || entry.de?.term || '(no anchor)';
    if (!/^[a-z][a-z0-9-]*$/.test(entry.anchor ?? '')) {
      problems.push({ kind: 'anchor', anchor: name, message: `the entry "${name}" has no anchor of small letters, digits and hyphens` });
    }
    if (seen.has(entry.anchor)) {
      problems.push({ kind: 'anchor', anchor: name, message: `the anchor "${name}" stands for two entries` });
    }
    seen.add(entry.anchor);
    for (const lang of ['en', 'de']) {
      for (const part of ['term', 'explanation']) {
        if (typeof entry[lang]?.[part] !== 'string' || entry[lang][part].trim() === '') {
          problems.push({ kind: 'counterpart', anchor: name, message: `the entry "${name}" has no ${part} in "${lang}"` });
        }
      }
    }
  }
  return problems;
}

const short = (problems) => problems.map((found) => `${found.kind}:${found.anchor}`).sort();

/** The check on pages it sets itself: it fails and passes as it must. */
async function proveItself(browser, origin) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const link = (lang, anchor, text) =>
    `<a data-term="${anchor}" href="${glossaryAddress[lang]}#${anchor}">${text}</a>`;
  // The page head and the page links name terms too; neither counts.
  const frame = (lang, body) => `<!doctype html><html lang="${lang}"><body><main>
    <div data-page-head><p>Stage</p><h1>Deviation, Abweichung</h1><p>A lead on the deviation, die Abweichung.</p></div>
    ${body}
    <nav data-page-links><a href="#">Reference model, Referenzmodell</a></nav>
  </main></body></html>`;
  const cases = [
    ['an unlinked term', 'en', '<p>A deviation shows.</p>', ['unlinked:deviation'], 'A deviation shows.'],
    ['a linked first occurrence, the term again as text', 'en', `<p>Two ${link('en', 'deviation', 'deviations')} show. Each deviation counts.</p>`, []],
    ['a term linked after its first occurrence', 'en', `<p>A deviation shows.</p><p>The ${link('en', 'deviation', 'deviation')} again.</p>`, ['unlinked:deviation']],
    ['a term linked twice', 'en', `<p>A ${link('en', 'deviation', 'deviation')} and two ${link('en', 'deviation', 'deviations')}.</p>`, ['twice:deviation'], '"Deviation"'],
    ['a term linked in a heading and in the text', 'en', `<h2>The ${link('en', 'deviation', 'deviation')}</h2><p>A ${link('en', 'deviation', 'deviation')} shows.</p>`, ['twice:deviation']],
    ['an unlinked term in content that is not shown', 'en', `<p>A ${link('en', 'deviation', 'deviation')} shows.</p><div style="display: none"><p>A revision.</p></div>`, ['unlinked:revision']],
    ['a term in the code of the page and in the name of a drawing', 'en', '<p>Text.</p><style>.record { color: inherit }</style><script>const value = 1; // a deviation</script><noscript><p>A revision.</p></noscript><svg><title>Value</title><desc>A class.</desc></svg>', []],
    ['a link to an unknown entry', 'en', `<p>${link('en', 'no-such-entry', 'Something')}</p>`, ['unknown:no-such-entry']],
    ['a link to the Glossary of the other language', 'en', `<p>A ${link('de', 'deviation', 'deviation')}.</p>`, ['address:deviation']],
    ['a word in an exempt passage, in code, in a heading, in another link', 'en', '<h2>Deviation</h2><p>Run <code>deviation</code>, <span data-no-term>a deviation from the plan</span>, <a href="/x">the deviation page</a>.</p><pre>deviation</pre>', []],
    ['a term inside a longer word', 'en', '<p>A deviational effect. Revisionism.</p>', []],
    ['a term without regard to case, and a form', 'en', '<p>REVISIONS and a Tolerance\n profile.</p>', ['unlinked:revision', 'unlinked:tolerance-profile']],
    ['two terms in two blocks', 'en', '<ul><li>Value</li><li>Record</li></ul>', ['unlinked:record', 'unlinked:value']],
    ['a term over two blocks', 'en', '<ul><li>Not</li><li>resolved</li></ul>', []],
    ['German: the case as written, a longer word', 'de', '<p>Das ist es wert. Eine Abweichungssumme.</p>', []],
    ['German: an unlinked term', 'de', '<p>Jeder Wert zählt.</p>', ['unlinked:value'], 'Jeder Wert zählt.'],
    ['German: an unlinked form', 'de', '<p>Die Summe der Abweichungen.</p>', ['unlinked:deviation']],
    ['German: a linked form', 'de', `<p>Die Summe der ${link('de', 'deviation', 'Abweichungen')}. Jede Abweichung zählt.</p>`, []],
  ];
  for (const [name, lang, body, expected, words] of cases) {
    await page.setContent(frame(lang, body));
    const problems = inspect(await readContent(page), lang, { looks: false });
    const found = short(problems);
    expect(
      found.join() === [...expected].sort().join(),
      `self-test "${name}": the check reports [${found.join(', ')}], expected [${expected.join(', ')}]`,
    );
    if (words) {
      expect(
        problems.some((problem) => problem.message.includes(words)),
        `self-test "${name}": no message holds ${words}: ${problems.map((problem) => problem.message).join(' | ')}`,
      );
    }
  }

  // The looks, on a page of the built site with its stylesheet: a glossary
  // link put into its content passes with the class of the glossary link and
  // fails without it.
  const stub = pages.find((entry) => entry.lang === 'en' && !isGlossary(entry));
  for (const [name, style, expected] of [
    ['a glossary link with its looks', 'glossary-link', []],
    ['a glossary link without its looks', '', ['looks:deviation']],
  ]) {
    await page.goto(`${origin}${stub.address}`);
    await page.evaluate(
      ({ style, href }) => {
        const paragraph = document.createElement('p');
        const anchor = document.createElement('a');
        anchor.className = style;
        anchor.dataset.term = 'deviation';
        anchor.href = href;
        anchor.textContent = 'deviation';
        paragraph.append('A ', anchor, ' shows.');
        document.querySelector('main [data-page-head]').after(paragraph);
      },
      { style, href: `${glossaryAddress.en}#deviation` },
    );
    // Only the looks are judged here; what else the page holds is its own.
    const found = short(inspect(await readContent(page), 'en')).filter((problem) =>
      problem.startsWith('looks:'),
    );
    expect(
      found.join() === expected.join(),
      `self-test "${name}" on ${stub.address}: the check reports [${found.join(', ')}], expected [${expected.join(', ')}]`,
    );
  }
  await context.close();

  // The register: an entry without its counterpart, an anchor twice.
  const whole = { anchor: 'whole', en: { term: 'Whole', forms: [], explanation: 'Text.' }, de: { term: 'Ganz', forms: [], explanation: 'Text.' } };
  const registers = [
    ['a whole entry', [whole], []],
    ['an entry without a German explanation', [{ ...whole, anchor: 'half', de: { term: 'Halb', forms: [], explanation: ' ' } }], ['counterpart:half']],
    ['an entry without an English term', [{ ...whole, anchor: 'half', en: { forms: [], explanation: 'Text.' } }], ['counterpart:half']],
    ['an anchor that stands for two entries', [whole, whole], ['anchor:whole']],
  ];
  for (const [name, entries, expected] of registers) {
    const found = short(inspectRegister(entries));
    expect(
      found.join() === expected.join(),
      `self-test "${name}": the check reports [${found.join(', ')}], expected [${expected.join(', ')}]`,
    );
  }
}

/** The entries of a language in its alphabetical order, each with its letter. */
function expectedOrder(lang) {
  const collator = new Intl.Collator(lang);
  return [...glossary.entries]
    .sort((a, b) => collator.compare(a[lang].term, b[lang].term))
    .map((entry) => ({
      entry,
      // Ä stands under A.
      letter: entry[lang].term.normalize('NFD').charAt(0).toUpperCase(),
    }));
}

/** Reads the Glossary in the open page: index, labels and entries in order. */
function readGlossary(page) {
  return page.evaluate(() => {
    const text = (element) => (element?.textContent ?? '').trim().replace(/\s+/g, ' ');
    const main = document.querySelector('main');
    const index = main.querySelector('nav[data-letter-index]');
    return {
      indexes: main.querySelectorAll('nav[data-letter-index]').length,
      indexLabel: index?.getAttribute('aria-label'),
      index: [...(index?.querySelectorAll('a') ?? [])].map((link) => {
        const target = document.getElementById((link.getAttribute('href') ?? '').slice(1));
        return {
          letter: text(link),
          href: link.getAttribute('href'),
          target: target?.matches('[data-letter]') ? text(target) : null,
          own: target?.hasAttribute('data-language-own') ?? false,
        };
      }),
      parts: [...main.querySelectorAll('[data-letter], [data-glossary-entry]')].map((part) => {
        if (part.matches('[data-letter]')) return { letter: text(part) };
        const term = part.querySelector('dt [data-term-name]');
        const counterpart = part.querySelector('dt [data-counterpart-term]');
        const word = counterpart?.querySelector('[lang]');
        return {
          anchor: part.id,
          inList: part.parentElement?.tagName === 'DL',
          groups: `${part.querySelectorAll(':scope > dt').length} dt, ${part.querySelectorAll(':scope > dd').length} dd`,
          term: text(term),
          termLang: term?.getAttribute('lang') ?? null,
          code: text(counterpart?.firstElementChild),
          counterpart: text(word),
          counterpartLang: word?.getAttribute('lang') ?? null,
          explanation: text(part.querySelector('dd > p')),
          appearsIn: text(part.querySelector('[data-appears-in]')),
          appearsOn: [...part.querySelectorAll('[data-appears-in] a')].map((link) => link.getAttribute('href')),
        };
      }),
    };
  });
}

/** Which entries show which cues of the linked state. */
function readLinkedState(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-glossary-entry]')].map((entry) => {
      const style = getComputedStyle(entry);
      const tag = entry.querySelector('dt .glossary-linked');
      const shown = tag !== null && getComputedStyle(tag).display !== 'none' && tag.getClientRects().length > 0;
      return {
        anchor: entry.id,
        ground: style.backgroundColor,
        bar: style.borderLeftColor,
        barWidth: style.borderLeftWidth,
        tag: shown ? tag.textContent.trim() : null,
      };
    }),
  );
}

/** The Glossary of a language; returns the anchors of its entries. */
async function checkGlossary(browser, origin, entry, javaScript, linkedOn) {
  const name = `${entry.address} (JavaScript ${javaScript ? 'on' : 'off'})`;
  const lang = entry.lang;
  const other = entry.otherLang;
  const context = await browser.newContext({ javaScriptEnabled: javaScript });
  const page = await context.newPage();
  const response = await page.goto(`${origin}${entry.address}`);
  expect(response?.status() === 200, `${name}: status ${response?.status()}, expected 200`);
  const built = await readGlossary(page);
  const order = expectedOrder(lang);
  const letters = [...new Set(order.map((item) => item.letter))];

  // The letter index: a labelled navigation of the letters that have entries.
  expect(built.indexes === 1, `${name}: ${built.indexes} letter indexes, expected 1`);
  expect(
    built.indexLabel === entry.texts.letters,
    `${name}: the letter index is labelled "${built.indexLabel}", expected "${entry.texts.letters}"`,
  );
  expect(
    built.index.map((link) => link.letter).join() === letters.join(),
    `${name}: the letter index names [${built.index.map((link) => link.letter)}], expected [${letters}]`,
  );
  for (const link of built.index) {
    expect(
      link.target === link.letter,
      `${name}: letter "${link.letter}" of the index leads to ${link.href}, which is not its label`,
    );
    expect(link.own, `${name}: the label of letter "${link.letter}" is not marked as an anchor of its language`);
  }

  // Labels and entries in the alphabetical order of the language.
  const expected = [];
  for (const [index, item] of order.entries()) {
    if (order[index - 1]?.letter !== item.letter) expected.push(`letter ${item.letter}`);
    expected.push(item.entry.anchor);
  }
  const found = built.parts.map((part) => part.anchor ?? `letter ${part.letter}`);
  expect(
    found.join() === expected.join(),
    `${name}: labels and entries stand as [${found.join(', ')}], expected [${expected.join(', ')}]`,
  );

  for (const part of built.parts.filter((item) => item.anchor)) {
    const item = glossary.findEntry(part.anchor);
    if (!item) {
      failures.push(`${name}: the entry "${part.anchor}" is not in the glossary register`);
      continue;
    }
    const at = `${name}: entry "${part.anchor}"`;
    expect(part.inList && part.groups === '1 dt, 1 dd', `${at} is not a term and its description in a description list`);
    expect(part.term === item[lang].term, `${at} shows the term "${part.term}", expected "${item[lang].term}"`);
    const termLang = item.termLang && item.termLang !== lang ? item.termLang : null;
    expect(part.termLang === termLang, `${at}: the term carries lang="${part.termLang}", expected ${termLang}`);
    expect(
      part.counterpart === item[other].term && part.code === other.toUpperCase(),
      `${at} shows the counterpart "${part.code} ${part.counterpart}", expected "${other.toUpperCase()} ${item[other].term}"`,
    );
    expect(
      part.counterpartLang === (item.termLang ?? other),
      `${at}: the counterpart carries lang="${part.counterpartLang}", expected "${item.termLang ?? other}"`,
    );
    const explanation = item[lang].explanation.replace(/<[^>]+>/g, '').trim().replace(/\s+/g, ' ');
    expect(part.explanation === explanation, `${at} shows the explanation "${part.explanation}", expected "${explanation}"`);

    // "Appears in": the pages that link the term, in path order.
    const on = linkedOn.get(part.anchor) ?? [];
    expect(
      part.appearsOn.join() === on.join(),
      `${at}: "${entry.texts.appearsIn}" lists [${part.appearsOn.join(', ')}], expected [${on.join(', ')}]`,
    );
    expect(
      on.length === 0 ? part.appearsIn === '' : part.appearsIn.startsWith(`${entry.texts.appearsIn}:`),
      `${at}: the line of its pages reads "${part.appearsIn}"`,
    );
  }

  // Every entry address: that entry shows the linked state, no other does.
  const plain = (state) => state.ground === NONE && state.bar === NONE && state.tag === null;
  for (const anchor of built.parts.map((part) => part.anchor).filter(Boolean)) {
    await page.goto(`${origin}${entry.address}#${anchor}`);
    for (const state of await readLinkedState(page)) {
      if (state.anchor === anchor) {
        expect(
          state.ground === GROUND && state.bar === BAR && state.barWidth === '2px' && state.tag === entry.texts.linkedTerm,
          `${name}: at #${anchor} the entry does not show the linked state (ground ${state.ground}, bar ${state.barWidth} ${state.bar}, tag "${state.tag}")`,
        );
      } else {
        expect(plain(state), `${name}: at #${anchor} the entry "${state.anchor}" shows the linked state too`);
      }
    }
  }
  // The state ends when the address changes.
  await page.goto(`${origin}${entry.address}#main`);
  for (const state of await readLinkedState(page)) {
    expect(plain(state), `${name}: at #main the entry "${state.anchor}" still shows the linked state`);
  }
  await context.close();
  return built.parts.map((part) => part.anchor).filter(Boolean);
}

for (const found of inspectRegister(glossary.entries)) {
  failures.push(`glossary register: ${found.message}`);
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
  browser = await chromium.launch();
  await proveItself(browser, origin);

  // The pages but the Glossaries: their glossary links. What each links is
  // kept per language, in path order, for "Appears in".
  const linkedOn = { de: new Map(), en: new Map() };
  const context = await browser.newContext();
  const page = await context.newPage();
  for (const entry of pages.filter((item) => !isGlossary(item))) {
    // An error on one page is a failure of that page; the others still run.
    try {
      const response = await page.goto(`${origin}${entry.address}`);
      if (response?.status() !== 200) {
        failures.push(`${entry.address}: status ${response?.status()}, expected 200`);
        continue;
      }
      const content = await readContent(page);
      for (const found of inspect(content, entry.lang)) {
        failures.push(`${entry.address}: ${found.message}`);
      }
      for (const anchor of new Set((content?.all ?? []).map((link) => link.anchor))) {
        const on = linkedOn[entry.lang];
        on.set(anchor, [...(on.get(anchor) ?? []), entry.address]);
      }
    } catch (error) {
      failures.push(`${entry.address}: ${error.stack ?? error.message}`);
    }
  }
  await context.close();

  // The Glossaries, with JavaScript on and off.
  const anchors = {};
  for (const entry of pages.filter(isGlossary)) {
    for (const javaScript of [true, false]) {
      try {
        anchors[entry.lang] = await checkGlossary(browser, origin, entry, javaScript, linkedOn[entry.lang]);
      } catch (error) {
        failures.push(`${entry.address}: ${error.stack ?? error.message}`);
      }
    }
  }
  // The way back: a glossary link of a page leads to the entry, which then
  // holds a link back; a click on it returns to the page. Opened directly,
  // from a Glossary or from outside the documentation, and when the address
  // changes, the entry holds no such link.
  for (const lang of Object.keys(linkedOn)) {
    const from = pages.find((entry) => entry.lang === lang && !isGlossary(entry) && [...linkedOn[lang].values()].some((on) => on.includes(entry.address)));
    if (!from) {
      failures.push(`no page of "${lang}" links a term; the way back from the Glossary is not checked`);
      continue;
    }
    const name = `${from.address}, the way back from the Glossary`;
    const text = backTexts[lang];
    const back = await browser.newContext();
    try {
      const page = await back.newPage();
      await page.goto(`${origin}${from.address}`);
      const term = page.locator('main a[data-term]').first();
      const anchor = await term.getAttribute('data-term');
      await term.click();
      await page.waitForURL(`${origin}${glossaryAddress[lang]}#${anchor}`);
      const link = page.locator(`#${anchor} [data-glossary-back] a`);
      await link.waitFor({ state: 'visible', timeout: 5_000 }).catch(() => {});
      expect(
        (await page.locator('[data-glossary-back]').count()) === 1 &&
          (await link.count()) === 1 &&
          (await link.innerText()).trim() === text &&
          (await link.getAttribute('href')) === `${origin}${from.address}`,
        `${name}: the entry "${anchor}" does not hold the one link "${text}" to ${from.address}`,
      );
      if ((await link.count()) === 1) {
        await link.click();
        await page.waitForURL(`${origin}${from.address}`, { timeout: 5_000 }).catch(() => {});
        expect(page.url() === `${origin}${from.address}`, `${name}: a click on "${text}" leads to ${page.url()}`);
        // The link goes when the address changes.
        await page.goForward();
        await page.waitForURL(`${origin}${glossaryAddress[lang]}#${anchor}`);
        await link.waitFor({ state: 'visible', timeout: 5_000 }).catch(() => {});
        expect(
          (await page.locator('[data-glossary-back]').count()) === 1,
          `${name}: back on the entry by the history, it does not hold the one link back`,
        );
        await page.evaluate(() => {
          window.location.hash = '#main';
        });
        await page.waitForFunction(() => window.location.hash === '#main');
        expect(
          (await page.locator('[data-glossary-back]').count()) === 0,
          `${name}: the link back stays when the address changes`,
        );
      }
      // Opened directly, and from the Glossary itself: no link.
      const direct = await back.newPage();
      await direct.goto(`${origin}${glossaryAddress[lang]}#${anchor}`, { waitUntil: 'networkidle' });
      expect((await direct.locator('[data-glossary-back]').count()) === 0, `${name}: opened directly, the entry holds a link back`);
      await direct.goto(`${origin}${glossaryAddress[lang]}`, { waitUntil: 'networkidle' });
      await direct.goto(`${origin}${glossaryAddress[lang]}#${anchor}`, {
        waitUntil: 'networkidle',
        referer: `${origin}${glossaryAddress[lang]}`,
      });
      await direct.reload({ waitUntil: 'networkidle' });
      expect((await direct.locator('[data-glossary-back]').count()) === 0, `${name}: arrived from the Glossary itself, the entry holds a link back`);
      // What the page names as the page before decides. A page of the
      // documentation gives the link; this also shows that the cases after it
      // can fail. Another site, an address of this origin outside the
      // documentation, and the Glossary of the other language give none.
      const arrive = async (referer) => {
        const arrived = await back.newPage();
        await arrived.goto('about:blank');
        await arrived.goto(`${origin}${glossaryAddress[lang]}#${anchor}`, { waitUntil: 'networkidle', referer });
        const count = await arrived.locator('[data-glossary-back]').count();
        await arrived.close();
        return count;
      };
      expect(
        (await arrive(`${origin}${from.address}`)) === 1,
        `${name}: arrived with ${from.address} as the page before, the entry does not hold the one link back`,
      );
      const other = lang === 'de' ? 'en' : 'de';
      for (const [way, referer] of [
        ['another site', 'https://example.org/'],
        ['an address of this origin outside the documentation', `${origin}/`],
        ['the Glossary of the other language', `${origin}${glossaryAddress[other]}`],
      ]) {
        expect((await arrive(referer)) === 0, `${name}: arrived from ${way} (${referer}), the entry holds a link back`);
      }
      // The language switch keeps the anchor: from the entry on the other
      // Glossary to this one, and no link back.
      const switched = await back.newPage();
      await switched.goto(`${origin}${glossaryAddress[other]}#${anchor}`, { waitUntil: 'networkidle' });
      await switched.locator('a[data-counterpart]').click();
      await switched.waitForURL(`${origin}${glossaryAddress[lang]}#${anchor}`);
      await switched.waitForLoadState('networkidle');
      expect(
        (await switched.locator('[data-glossary-back]').count()) === 0,
        `${name}: arrived by the language switch from ${glossaryAddress[other]}, the entry holds a link back`,
      );
    } catch (error) {
      failures.push(`${name}: ${error.stack ?? error.message}`);
    }
    await back.close();
  }

  // The two Glossaries hold the same entries.
  for (const [lang, other] of [
    ['de', 'en'],
    ['en', 'de'],
  ]) {
    for (const anchor of anchors[lang] ?? []) {
      expect(
        (anchors[other] ?? []).includes(anchor),
        `${glossaryAddress[lang]}: the entry "${anchor}" is missing on the Glossary of the other language, ${glossaryAddress[other]}`,
      );
    }
  }
  for (const entry of glossary.entries) {
    for (const lang of ['de', 'en']) {
      expect(
        (anchors[lang] ?? []).includes(entry.anchor),
        `${glossaryAddress[lang]}: the entry "${entry.anchor}" of the glossary register is not on the page`,
      );
    }
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(
  `the ${glossary.entries.length} entries of both Glossaries and the glossary links of all ${pages.length} pages pass`,
);
