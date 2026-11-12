// The language switch keeps the position: the anchor of the current address
// (a step, a glossary entry) is added to the link to the counterpart, at the
// load and whenever the anchor changes. The anchor of a step or an entry is
// the same in both languages. An anchor that belongs to one language (a
// letter label of the Glossary) is carried along too; the counterpart then
// opens at the top, or at that letter of the other language where it has
// one. Without this script the counterpart opens at the top.

// Each link with the address the page was delivered with.
const links = [...document.querySelectorAll<HTMLAnchorElement>('a[data-counterpart]')].map(
  (link) => ({ link, address: link.getAttribute('href') ?? '' }),
);

function keepAnchor(): void {
  for (const { link, address } of links) {
    link.setAttribute('href', `${address}${window.location.hash}`);
  }
}

keepAnchor();
window.addEventListener('hashchange', keepAnchor);
