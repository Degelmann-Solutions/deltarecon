// Checks the hint list and the contact block of "When something goes wrong"
// and the hint links that lead to it, on the built site in Chromium. Run
// after the build: `npm run check`.
//
// The register of the hint groups (src/hints.ts) names every group: its
// anchor on the help page, its page and the step or section it belongs to.
// The help page builds its groups from it and a step reads its hint link
// from it. This script holds both directions against the register, in both
// languages:
//   - the register itself (`groupFaults`): anchors of small letters, digits
//     and hyphens, each once; pages of the page register, in path order; one
//     group per step or section;
//   - the help page shows exactly the groups of the register, in its order,
//     and the groups of one page in the order of its steps or sections;
//   - a group names a step or a section that its page holds; its label names
//     page and step ("Quick start · step 1"; for a section the word
//     "section"); its heading is the title of the step card or the heading
//     of the section, a level-2 section heading with the anchor of the
//     group; it holds at least one hint, each a level-3 title with a text;
//     its one link leads to the step, by the title of the step;
//   - a step or a section with a group carries exactly one hint link, inside
//     it, in the words of the language, to its group on the help page of the
//     language; no other step or section carries one;
//   - both languages hold the same groups and the same hint links;
//   - followed in the browser: every hint link opens the help page of its
//     language at its group, and the link of the group leads back to the
//     step or section.
// First it proves itself: on the facts it has read, altered in one place
// each (a group whose step is not there, a hint link without a group, a
// group whose step carries no hint link, a group and a hint link in one
// language only, a group out of order), it must name the fault with the
// group, the step or the page. And `groupFaults` must name an unknown page,
// an anchor that stands twice and a group out of path order.
//
// The contact block: the last block of the page, under the last section
// heading; e-mail, phone and address are those of `contact` in src/site.ts,
// the e-mail a `mailto:` link, phone and address text; its title is a
// level-3 heading; the list of what to tell names the release of
// src/release.json.
//
// The looks (DESIGN.md, Components: Help), at 1280, 390 and 320 px: the
// group label in mono 12 px capitals outside the heading, the heading in
// 22 px (20 px on the phone); a hint with a hairline above, at 1280 px in
// two columns, the left 260 px wide and 36 px from the right, at 390 and
// 320 px in one column; hint titles 16 px, 600; a quoted message in the
// white mono box; the contact block with a 1 px navy border and 24 px
// padding (16 px on the phone), the e-mail in mono 18 px, underlined, the
// values 16 px and below their labels on the phone; no sideways scrolling.
//
// Writes to screenshots/ (not under version control) `help-desktop-<lang>.png`
// and `help-phone-<lang>.png`. Lay them beside the mock of the page.
// Exits non-zero and names page and part of every failed expectation.
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import {
  BASE,
  DESKTOP,
  PHONE,
  expectations,
  loadHints,
  loadPages,
  loadRegister,
  loadRelease,
  pageChecks,
  root,
  startPreview,
} from './harness.mjs';

const { failures, expect, report } = expectations('check-hints');
const { checkNoSidewaysScroll } = pageChecks({ failures, expect });
const site = await loadRegister();
const hints = await loadHints();
const pages = await loadPages();
const release = await loadRelease();

/** The narrowest width a page is looked at. */
const NARROW = { width: 320, height: 844 };
const NAVY = 'rgb(30, 37, 71)';
const TEAL_TEXT = 'rgb(23, 121, 130)';
const SECONDARY = 'rgb(58, 64, 96)';
const BORDER = 'rgb(229, 232, 237)';

/**
 * The words of a group and of a hint link, written out per language, so that
 * a changed text fails here until both places agree.
 */
const words = {
  en: {
    step: (number) => `step ${number}`,
    section: 'section',
    linkStep: 'If something goes wrong at this step',
    linkSection: 'If something goes wrong in this section',
    toStep: 'To the step:',
    toSection: 'To the section:',
    labels: ['E-mail', 'Phone', 'Address'],
  },
  de: {
    step: (number) => `Schritt ${number}`,
    section: 'Abschnitt',
    linkStep: 'Wenn bei diesem Schritt etwas schiefgeht',
    linkSection: 'Wenn in diesem Abschnitt etwas schiefgeht',
    toStep: 'Zum Schritt:',
    toSection: 'Zum Abschnitt:',
    labels: ['E-Mail', 'Telefon', 'Anschrift'],
  },
};

const help = site.findPage(hints.helpPage);
const addressOf = (id, lang) => `${BASE}${site.pagePath(site.findPage(id), lang)}`;

/** What a built page holds of steps, sections, hint links and groups. */
function readPage() {
  const text = (element) => (element?.textContent ?? '').replace(/\s+/g, ' ').trim();
  const headings = [...document.querySelectorAll('main h2[data-section-heading]')];
  return {
    steps: [...document.querySelectorAll('main li[data-step]')].map((step) => ({
      id: step.id,
      title: text(step.querySelector('.step-title')),
    })),
    sections: headings.map((heading) => ({ id: heading.id, title: text(heading) })),
    links: [...document.querySelectorAll('[data-hint-link]')].map((line) => {
      const step = line.closest('main li[data-step]');
      const before = headings.filter(
        (heading) => heading.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING,
      );
      const anchors = [...line.querySelectorAll('a')];
      return {
        group: line.getAttribute('data-hint-link'),
        of: line.getAttribute('data-hint-of'),
        kind: step ? 'step' : 'section',
        within: step ? step.id : (before.pop()?.id ?? ''),
        anchors: anchors.length,
        href: anchors[0]?.getAttribute('href') ?? '',
        text: text(line),
      };
    }),
    groups: [...document.querySelectorAll('main [data-hint-group]')].map((group) => {
      const heading = group.querySelector('h2');
      const label = group.querySelector('[data-hint-group-label]');
      const back = group.querySelector('[data-hint-back]');
      const backLinks = [...(back?.querySelectorAll('a') ?? [])];
      return {
        anchor: group.getAttribute('data-hint-group'),
        label: text(label),
        labelInHeading: label?.closest('h1, h2, h3, h4, h5, h6') !== null,
        labelFirst: group.firstElementChild === label && label?.nextElementSibling === heading,
        heading: heading
          ? { id: heading.id, title: text(heading), section: heading.hasAttribute('data-section-heading') }
          : null,
        hints: [...group.querySelectorAll('[data-hint]')].map((hint) => ({
          title: text(hint.querySelector('.hint-title')),
          tag: hint.querySelector('.hint-title')?.tagName ?? '',
          text: text(hint.querySelector('.hint-text')),
        })),
        back: {
          links: backLinks.length,
          href: backLinks[0]?.getAttribute('href') ?? '',
          title: text(backLinks[0]),
          line: text(back),
        },
      };
    }),
  };
}

/**
 * What is wrong between the register and what the built pages of one
 * language hold, one sentence per fault. `facts` maps the id of a page to
 * what `readPage` gave for it.
 */
function faultsOf(lang, groups, facts) {
  const found = [];
  const w = words[lang];
  const helpFacts = facts[hints.helpPage];
  const helpAddress = addressOf(hints.helpPage, lang);
  const shown = helpFacts.groups.map((group) => group.anchor);
  const listed = groups.map((group) => group.anchor);
  if (JSON.stringify(shown) !== JSON.stringify(listed)) {
    found.push(`${helpAddress}: the groups are [${shown}], the register (src/hints.ts) names [${listed}]`);
  }

  let lastPage;
  let lastIndex = -1;
  for (const group of groups) {
    const name = `the hint group "${group.anchor}" (${lang})`;
    const pageAddress = addressOf(group.page, lang);
    const pageFacts = facts[group.page];
    const parts = group.kind === 'step' ? pageFacts.steps : pageFacts.sections;
    const index = parts.findIndex((part) => part.id === group.target);
    if (index === -1) {
      found.push(`${name} names the ${group.kind} "${group.target}", which the page ${pageAddress} does not hold`);
      continue;
    }
    if (group.page === lastPage && index < lastIndex) {
      found.push(`${name} stands after a group of a later ${group.kind} of the page ${pageAddress}`);
    }
    lastPage = group.page;
    lastIndex = index;

    // The step or the section carries exactly one hint link, to this group.
    const carried = pageFacts.links.filter((link) => link.kind === group.kind && link.within === group.target);
    if (carried.length !== 1) {
      found.push(
        `${name}: the ${group.kind} "${group.target}" of the page ${pageAddress} carries ${carried.length === 0 ? 'no hint link' : `${carried.length} hint links`}`,
      );
    }

    const built = helpFacts.groups.find((entry) => entry.anchor === group.anchor);
    if (!built) continue;
    const title = parts[index].title;
    const label =
      group.kind === 'step'
        ? `${site.findPage(group.page).name[lang]} · ${w.step(index + 1)}`
        : `${site.findPage(group.page).name[lang]} · ${w.section}`;
    if (built.label !== label) found.push(`${name}: its label is "${built.label}", expected "${label}"`);
    if (built.labelInHeading || !built.labelFirst) {
      found.push(`${name}: its label does not stand before its heading and outside it`);
    }
    if (!built.heading || !built.heading.section || built.heading.id !== group.anchor) {
      found.push(`${name}: its heading is no section heading with the anchor of the group`);
    } else if (built.heading.title !== title) {
      found.push(`${name}: its heading is "${built.heading.title}", the ${group.kind} is called "${title}"`);
    }
    if (built.hints.length === 0) found.push(`${name} holds no hint`);
    for (const hint of built.hints) {
      if (hint.tag !== 'H3' || hint.title === '') found.push(`${name}: a hint has no level-3 title ("${hint.title}")`);
      if (hint.text.length < 20) found.push(`${name}: the hint "${hint.title}" has no text`);
    }
    const target = `${pageAddress}#${group.target}`;
    const before = group.kind === 'step' ? w.toStep : w.toSection;
    if (built.back.links !== 1 || built.back.href !== target) {
      found.push(`${name}: its link leads to "${built.back.href}", expected ${target}`);
    }
    if (built.back.title !== title || built.back.line !== `${before} ${title}`) {
      found.push(`${name}: its link reads "${built.back.line}", expected "${before} ${title}"`);
    }
  }

  // Every hint link of every page: inside the step or section it names, to
  // a group the help page holds, in the words of the language.
  for (const [id, pageFacts] of Object.entries(facts)) {
    const pageAddress = addressOf(id, lang);
    for (const link of pageFacts.links) {
      const name = `${pageAddress}: the hint link of the ${link.kind} "${link.within}"`;
      const group = groups.find((entry) => entry.anchor === link.group);
      if (!group || !shown.includes(link.group)) {
        found.push(`${name} leads to the group "${link.group}", which the help page ${helpAddress} does not hold`);
        continue;
      }
      if (group.page !== id || group.kind !== link.kind || group.target !== link.within || link.of !== link.within) {
        found.push(`${name} leads to the group "${link.group}", which belongs to the ${group.kind} "${group.target}" of the page "${group.page}"`);
      }
      if (link.anchors !== 1 || link.href !== `${helpAddress}#${link.group}`) {
        found.push(`${name} leads to "${link.href}", expected ${helpAddress}#${link.group}`);
      }
      const text = link.kind === 'step' ? w.linkStep : w.linkSection;
      if (link.text !== text) found.push(`${name} reads "${link.text}", expected "${text}"`);
    }
  }
  return found;
}

/** What differs between the two languages: groups and hint links. */
function languageFaults(factsByLang) {
  const found = [];
  const [first, second] = site.languages;
  const key = (facts) => ({
    groups: facts[hints.helpPage].groups.map((group) => group.anchor),
    links: Object.fromEntries(
      Object.entries(facts).map(([id, pageFacts]) => [
        id,
        pageFacts.links.map((link) => `${link.kind} ${link.within} -> ${link.group}`),
      ]),
    ),
  });
  const a = key(factsByLang[first]);
  const b = key(factsByLang[second]);
  if (JSON.stringify(a.groups) !== JSON.stringify(b.groups)) {
    found.push(
      `the help pages differ: ${addressOf(hints.helpPage, first)} holds the groups [${a.groups}], ${addressOf(hints.helpPage, second)} holds [${b.groups}]`,
    );
  }
  for (const id of Object.keys(a.links)) {
    if (JSON.stringify(a.links[id]) !== JSON.stringify(b.links[id])) {
      found.push(
        `the hint links of the page "${id}" differ by language: ${addressOf(id, first)} holds [${a.links[id]}], ${addressOf(id, second)} holds [${b.links[id]}]`,
      );
    }
  }
  return found;
}

/** The script on facts it alters itself: each fault must be named. */
function proveItself(factsByLang) {
  const copy = () => structuredClone(factsByLang);
  const groups = hints.hintGroups;
  const sample = groups[0];
  const named = (found, ...parts) => found.some((fault) => parts.every((part) => fault.includes(part)));
  const cases = [];

  // Matrix row 1: a group names a step its page does not hold.
  {
    const altered = groups.map((group) => (group === sample ? { ...group, target: 'not-there' } : group));
    cases.push([
      'a group whose step is not there',
      named(faultsOf('en', altered, factsByLang.en), `"${sample.anchor}"`, '"not-there"', addressOf(sample.page, 'en')),
    ]);
  }
  // Matrix row 2: a step carries a hint link whose group the help page does not hold.
  {
    const facts = copy();
    facts.en[sample.page].links.find((link) => link.group === sample.anchor).group = 'no-such-group';
    cases.push([
      'a hint link without a group',
      named(faultsOf('en', groups, facts.en), addressOf(sample.page, 'en'), `"${sample.target}"`, '"no-such-group"'),
    ]);
  }
  {
    const facts = copy();
    facts.en[hints.helpPage].groups = facts.en[hints.helpPage].groups.filter((group) => group.anchor !== sample.anchor);
    cases.push([
      'a hint link whose group the help page leaves out',
      named(faultsOf('en', groups, facts.en), `the hint link of the step "${sample.target}"`, 'does not hold'),
    ]);
  }
  // Matrix row 3: the step of a group carries no hint link.
  {
    const facts = copy();
    facts.en[sample.page].links = facts.en[sample.page].links.filter((link) => link.group !== sample.anchor);
    cases.push([
      'a group whose step carries no hint link',
      named(faultsOf('en', groups, facts.en), `"${sample.anchor}"`, 'carries no hint link'),
    ]);
  }
  // Matrix row 4: a group or a hint link in one language only.
  {
    const facts = copy();
    facts.de[hints.helpPage].groups.pop();
    cases.push(['a group in one language only', named(languageFaults(facts), 'the help pages differ', addressOf(hints.helpPage, 'de'))]);
  }
  {
    const facts = copy();
    facts.de[sample.page].links.shift();
    cases.push(['a hint link in one language only', named(languageFaults(facts), `"${sample.page}"`, addressOf(sample.page, 'de'))]);
  }
  // The order of the path, and a heading that is not the title of the step.
  {
    const altered = [groups[1], groups[0], ...groups.slice(2)];
    cases.push(['groups out of the order of the steps', named(faultsOf('en', altered, factsByLang.en), 'stands after a group of a later step')]);
  }
  {
    const facts = copy();
    facts.en[hints.helpPage].groups[0].heading.title = 'Another title';
    cases.push(['a heading that is not the title of the step', named(faultsOf('en', groups, facts.en), `"${sample.anchor}"`, 'Another title')]);
  }
  for (const [name, caught] of cases) {
    expect(caught, `the check does not prove itself: ${name} is not named`);
  }

  // The register check, on registers it sets itself.
  const ids = site.pages.map((page) => page.id);
  const entry = (page, target, anchor = `${page}-${target}`) => ({ anchor, page, kind: 'step', target });
  const registers = [
    ['an unknown page', [entry('no-such-page', 'download')], 'no-such-page'],
    ['an anchor twice', [entry('quick-start', 'download'), entry('quick-start', 'check', 'quick-start-download')], 'repeats an anchor'],
    ['two groups of one step', [entry('quick-start', 'download'), entry('quick-start', 'download', 'second')], 'second group'],
    ['pages out of path order', [entry('own-calculations', 'folder'), entry('quick-start', 'download')], 'order of the path'],
    ['an anchor in capitals', [entry('quick-start', 'download', 'Download')], 'small letters'],
    ['the help page itself', [entry(hints.helpPage, 'contact', 'own')], 'help page itself'],
  ];
  for (const [name, register, part] of registers) {
    expect(
      hints.groupFaults(register, ids).some((fault) => fault.includes(part)),
      `the check does not prove itself: groupFaults does not name ${name}`,
    );
  }
  expect(hints.groupFaults([entry('quick-start', 'download'), entry('own-calculations', 'folder')], ids).length === 0, 'the check does not prove itself: groupFaults names a fault of a register that holds');
}

async function open(browser, origin, address, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await page.goto(`${origin}${address}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('html[data-menu]');
  return { context, page };
}

/** Every hint link, followed: to the group, and from the group back. */
async function checkFollowed(browser, origin, lang) {
  const context = await browser.newContext({ viewport: DESKTOP });
  const page = await context.newPage();
  for (const group of hints.hintGroups) {
    const from = `${addressOf(group.page, lang)}#${group.target}`;
    const to = `${addressOf(hints.helpPage, lang)}#${group.anchor}`;
    const name = `${from}: the hint link`;
    await page.goto(`${origin}${from}`, { waitUntil: 'load' });
    const link = page.locator(`[data-hint-link="${group.anchor}"] a`);
    if ((await link.count()) !== 1) continue; // named by `faultsOf`
    await link.click();
    await page.waitForURL((url) => url.pathname !== new URL(`${origin}${from}`).pathname, { waitUntil: 'load', timeout: 10_000 }).catch(() => {});
    const there = new URL(page.url());
    expect(`${there.pathname}${there.hash}` === to, `${name} opens ${there.pathname}${there.hash}, expected ${to}`);
    const top = await page.evaluate((id) => document.getElementById(id)?.getBoundingClientRect().top, group.anchor);
    expect(
      top !== undefined && top >= -1 && top < DESKTOP.height,
      `${name}: the group "${group.anchor}" is not in the window after the click (top ${top})`,
    );
    const lang_ = await page.evaluate(() => document.documentElement.lang);
    expect(lang_ === lang, `${name} opens a page of the language "${lang_}"`);
    const back = page.locator(`[data-hint-group="${group.anchor}"] [data-hint-back] a`);
    if ((await back.count()) !== 1) continue;
    await back.click();
    await page.waitForURL((url) => url.pathname !== there.pathname, { waitUntil: 'load', timeout: 10_000 }).catch(() => {});
    const again = new URL(page.url());
    expect(
      `${again.pathname}${again.hash}` === from,
      `${to}: the link of the group opens ${again.pathname}${again.hash}, expected ${from}`,
    );
    const targetTop = await page.evaluate((id) => document.getElementById(id)?.getBoundingClientRect().top, group.target);
    expect(
      targetTop !== undefined && targetTop >= -1 && targetTop < DESKTOP.height,
      `${to}: the ${group.kind} "${group.target}" is not in the window after the click (top ${targetTop})`,
    );
  }
  await context.close();
}

/** The contact block: the details of the register, the release, its place. */
async function checkContact(page, name, lang) {
  const shown = await page.evaluate((anchor) => {
    const text = (element) => (element?.textContent ?? '').replace(/\s+/g, ' ').trim();
    const blocks = [...document.querySelectorAll('main [data-contact]')];
    const block = blocks[0];
    if (!block) return { blocks: 0 };
    const heading = document.querySelector(`main h2#${anchor}`);
    const headings = [...document.querySelectorAll('main h2')].filter((h2) => !h2.closest('[data-page-links]'));
    const email = block.querySelector('[data-contact-email]');
    const links = [...block.querySelectorAll('a')];
    return {
      blocks: blocks.length,
      afterHeading: heading?.nextElementSibling === block,
      lastHeading: headings[headings.length - 1] === heading,
      beforePageLinks: block.nextElementSibling?.hasAttribute('data-page-links') ?? false,
      title: { tag: block.querySelector('.contact-title')?.tagName ?? '', text: text(block.querySelector('.contact-title')) },
      tag: text(block.querySelector('.contact-tag')),
      labels: [...block.querySelectorAll('dl > dt')].map(text),
      values: [...block.querySelectorAll('dl > dd')].map(text),
      email: text(email),
      links: links.map((link) => link.getAttribute('href')),
      phoneLinks: block.querySelectorAll('[data-contact-phone] a, [data-contact-address] a').length,
      tell: [...block.querySelectorAll('[data-contact-tell] li')].map(text),
      forms: document.querySelectorAll('main form, main input, main textarea, main button[type="submit"]').length,
    };
  }, hints.contactAnchor);
  expect(shown.blocks === 1, `${name}: the page holds ${shown.blocks} contact blocks, expected one`);
  if (shown.blocks !== 1) return;
  const { contact } = site;
  expect(shown.afterHeading && shown.lastHeading, `${name}: the contact block does not stand under the last section heading, "#${hints.contactAnchor}"`);
  expect(shown.beforePageLinks, `${name}: the contact block is not the last block of the page`);
  expect(shown.title.tag === 'H3' && shown.title.text !== '', `${name}: the title of the contact block is no level-3 heading`);
  expect(shown.tag !== '', `${name}: the contact block has no tag`);
  expect(
    JSON.stringify(shown.labels) === JSON.stringify(words[lang].labels),
    `${name}: the labels of the contact block are [${shown.labels}], expected [${words[lang].labels}]`,
  );
  const expected = [contact.email, contact.phone, contact.address.join(', ')];
  expect(
    JSON.stringify(shown.values) === JSON.stringify(expected),
    `${name}: the contact details are [${shown.values.join(' | ')}], the register (src/site.ts, "contact") holds [${expected.join(' | ')}]`,
  );
  expect(
    JSON.stringify(shown.links) === JSON.stringify([`mailto:${contact.email}`]),
    `${name}: the links of the contact block are [${shown.links}], expected the e-mail alone`,
  );
  expect(shown.phoneLinks === 0, `${name}: phone or address of the contact block is a link`);
  expect(shown.tell.length === 4, `${name}: the contact block names ${shown.tell.length} things to tell, expected 4`);
  expect(
    shown.tell.some((item) => item.includes(`v${release}`)),
    `${name}: the list of what to tell does not name the release v${release}`,
  );
  expect(shown.forms === 0, `${name}: the page holds a form`);
}

/** The looks of the hint list and the contact block at one width. */
async function checkLooks(page, name, viewport) {
  const phone = viewport.width < 600;
  const looks = await page.evaluate(() => {
    const px = (value) => Number.parseFloat(value);
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width };
    };
    const group = document.querySelector('main [data-hint-group]');
    const label = group.querySelector('[data-hint-group-label]');
    const heading = group.querySelector('h2');
    const labelStyle = getComputedStyle(label);
    const list = group.querySelector('[data-hint-list]');
    const quote = document.querySelector('main [data-hint-quote]');
    const quoteStyle = quote ? getComputedStyle(quote) : null;
    const block = document.querySelector('main [data-contact]');
    const blockStyle = getComputedStyle(block);
    const email = block.querySelector('[data-contact-email] a');
    const emailStyle = getComputedStyle(email);
    const style = (selector) => getComputedStyle(block.querySelector(selector));
    return {
      window: document.documentElement.clientWidth,
      label: {
        size: px(labelStyle.fontSize),
        family: labelStyle.fontFamily,
        transform: labelStyle.textTransform,
        colour: labelStyle.color,
        gap: px(getComputedStyle(heading).marginTop),
      },
      heading: px(getComputedStyle(heading).fontSize),
      list: { width: box(list).width, closing: getComputedStyle(list).borderBottomWidth },
      hints: [...document.querySelectorAll('main [data-hint]')].map((hint) => {
        const title = hint.querySelector('.hint-title');
        const text = hint.querySelector('.hint-text');
        const titleStyle = getComputedStyle(title);
        const hintStyle = getComputedStyle(hint);
        return {
          name: title.textContent.trim(),
          title: box(title),
          text: box(text),
          hint: box(hint),
          size: px(titleStyle.fontSize),
          weight: titleStyle.fontWeight,
          rule: `${hintStyle.borderTopWidth} ${hintStyle.borderTopStyle} ${hintStyle.borderTopColor}`,
          padding: px(hintStyle.paddingTop),
          textSize: px(getComputedStyle(text).fontSize),
        };
      }),
      quote: quoteStyle && {
        family: quoteStyle.fontFamily,
        size: px(quoteStyle.fontSize),
        ground: quoteStyle.backgroundColor,
        border: quoteStyle.borderTopWidth,
        right: box(quote).right,
      },
      contact: {
        box: box(block),
        border: `${blockStyle.borderTopWidth} ${blockStyle.borderTopStyle} ${blockStyle.borderTopColor}`,
        radius: blockStyle.borderTopLeftRadius,
        padding: px(blockStyle.paddingTop),
        tagColour: style('.contact-tag').color,
        title: px(style('.contact-title').fontSize),
        pairs: [...block.querySelectorAll('dl > dt')].map((term) => ({
          label: box(term),
          value: box(term.nextElementSibling),
          labelSize: px(getComputedStyle(term).fontSize),
          labelTransform: getComputedStyle(term).textTransform,
          valueSize: px(getComputedStyle(term.nextElementSibling).fontSize),
          valueFamily: getComputedStyle(term.nextElementSibling).fontFamily,
        })),
        email: {
          colour: emailStyle.color,
          underline: emailStyle.textDecorationLine,
          family: emailStyle.fontFamily,
          height: box(email).bottom - box(email).top,
        },
        tell: px(style('[data-contact-tell]').fontSize),
        rule: style('[data-contact-tell]').borderTopWidth,
      },
    };
  });
  const near = (value, target, slack = 1) => Math.abs(value - target) <= slack;

  expect(
    looks.label.size === 12 && looks.label.family.includes('JetBrains Mono') && looks.label.transform === 'uppercase' && looks.label.colour === SECONDARY,
    `${name}: the group label is ${looks.label.size} px, ${looks.label.family}, ${looks.label.transform}, ${looks.label.colour}`,
  );
  expect(looks.label.gap === 4, `${name}: the group heading stands ${looks.label.gap} px below its label, expected 4`);
  expect(looks.heading === (phone ? 20 : 22), `${name}: the group heading is ${looks.heading} px, expected ${phone ? 20 : 22}`);
  expect(looks.list.width <= 900 && looks.list.closing === '1px', `${name}: the hint list is ${looks.list.width} px wide or lacks its closing hairline`);
  expect(looks.hints.length > 0, `${name}: the page holds no hint`);
  for (const hint of looks.hints) {
    const which = `${name}: the hint "${hint.name}"`;
    expect(hint.size === 16 && hint.weight === '600', `${which}: its title is ${hint.size} px, weight ${hint.weight}`);
    expect(hint.textSize === 16, `${which}: its text is ${hint.textSize} px`);
    expect(hint.rule === `1px solid ${BORDER}` && hint.padding === 16, `${which}: its hairline is "${hint.rule}", its padding ${hint.padding} px`);
    if (phone) {
      expect(
        near(hint.title.left, hint.text.left) && hint.text.top >= hint.title.bottom,
        `${which}: title and text do not stand in one column`,
      );
    } else {
      expect(
        near(hint.title.width, 260) && near(hint.text.left - hint.title.right, 36) && near(hint.title.top, hint.text.top, 2),
        `${which}: the left column is ${hint.title.width} px wide and ${hint.text.left - hint.title.right} px from the right one, expected 260 and 36`,
      );
    }
    expect(hint.text.right <= looks.window + 0.5, `${which} reaches beyond the window`);
  }
  expect(looks.quote !== null, `${name}: no hint quotes a message of the program`);
  if (looks.quote) {
    expect(
      looks.quote.family.includes('JetBrains Mono') && looks.quote.size === 12.5 && looks.quote.ground === 'rgb(255, 255, 255)' && looks.quote.border === '1px',
      `${name}: a quoted message is ${looks.quote.family}, ${looks.quote.size} px on ${looks.quote.ground}`,
    );
    expect(looks.quote.right <= looks.window + 0.5, `${name}: a quoted message reaches beyond the window`);
  }

  const contact = looks.contact;
  expect(
    contact.border === `1px solid ${NAVY}` && contact.radius === '2px' && contact.padding === (phone ? 16 : 24),
    `${name}: the contact block has the border "${contact.border}", radius ${contact.radius}, padding ${contact.padding} px`,
  );
  expect(contact.box.width <= 720 && contact.box.right <= looks.window + 0.5, `${name}: the contact block is ${contact.box.width} px wide or reaches beyond the window`);
  expect(contact.tagColour === TEAL_TEXT && contact.title === 18, `${name}: the tag of the contact block is ${contact.tagColour}, its title ${contact.title} px`);
  expect(contact.pairs.length === 3, `${name}: the contact block holds ${contact.pairs.length} pairs of label and value`);
  contact.pairs.forEach((pair, index) => {
    const which = `${name}: contact block, pair ${index + 1}`;
    expect(pair.labelSize === 11 && pair.labelTransform === 'uppercase', `${which}: the label is ${pair.labelSize} px, ${pair.labelTransform}`);
    const address = index === 2;
    const size = address ? 14 : phone ? 16 : 18;
    expect(pair.valueSize === size, `${which}: the value is ${pair.valueSize} px, expected ${size}`);
    expect(
      pair.valueFamily.includes(address ? 'Inter' : 'JetBrains Mono'),
      `${which}: the value is set in ${pair.valueFamily}`,
    );
    if (phone) {
      expect(
        pair.value.top >= pair.label.bottom - 0.5 && near(pair.value.left, pair.label.left),
        `${which}: the value does not stand below its label`,
      );
    } else {
      expect(pair.value.left >= pair.label.right, `${which}: the value does not stand right of its label`);
    }
    expect(pair.value.right <= contact.box.right, `${which}: the value reaches beyond the block`);
  });
  expect(
    contact.email.colour === TEAL_TEXT && contact.email.underline.includes('underline') && contact.email.family.includes('JetBrains Mono'),
    `${name}: the e-mail is ${contact.email.colour}, "${contact.email.underline}", ${contact.email.family}`,
  );
  expect(contact.email.height >= 24, `${name}: the e-mail link is ${contact.email.height} px high, below 24`);
  expect(contact.tell === 15 && contact.rule === '1px', `${name}: the list of what to tell is ${contact.tell} px, its hairline ${contact.rule}`);
  await checkNoSidewaysScroll(page, name);
}

const { origin: reported, stop } = startPreview();
let browser;
let links = 0;
try {
  const origin = await reported;
  browser = await chromium.launch();
  await mkdir(path.join(root, 'screenshots'), { recursive: true });

  for (const fault of hints.groupFaults(hints.hintGroups, site.pages.map((page) => page.id))) {
    failures.push(`src/hints.ts: ${fault}`);
  }

  // What every page of both languages holds.
  const factsByLang = {};
  {
    const context = await browser.newContext({ viewport: DESKTOP });
    const page = await context.newPage();
    for (const entry of pages) {
      await page.goto(`${origin}${entry.address}`);
      (factsByLang[entry.lang] ??= {})[entry.id] = await page.evaluate(readPage);
    }
    await context.close();
  }
  proveItself(factsByLang);
  for (const lang of site.languages) {
    failures.push(...faultsOf(lang, hints.hintGroups, factsByLang[lang]));
    links += Object.values(factsByLang[lang]).reduce((sum, facts) => sum + facts.links.length, 0);
  }
  failures.push(...languageFaults(factsByLang));

  for (const lang of site.languages) {
    await checkFollowed(browser, origin, lang);
    const address = `${BASE}${site.pagePath(help, lang)}`;
    for (const viewport of [DESKTOP, PHONE, NARROW]) {
      const { context, page } = await open(browser, origin, address, viewport);
      const name = `${address} (${viewport.width} px)`;
      if (viewport === DESKTOP) await checkContact(page, name, lang);
      await checkLooks(page, name, viewport);
      if (viewport !== NARROW) {
        await page.screenshot({
          path: path.join(root, 'screenshots', `help-${viewport === DESKTOP ? 'desktop' : 'phone'}-${lang}.png`),
          fullPage: true,
        });
      }
      await context.close();
    }
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(`${hints.hintGroups.length} hint groups and ${links} hint links in both languages, the contact block and their looks pass`);
