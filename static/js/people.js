/* Author block. This page is published anonymously; author details are not part of it. Where a separate author file is
   served from the same origin (/ROBUST-TAMP-authors/authors.json), its contents replace the anonymous header, BibTeX
   author line, footer and code link. Elsewhere the file is absent and the page stays anonymous. All text is inserted as
   text, never as HTML. */
(function () {
  'use strict';
  const root = document.documentElement;
  const base = new URL('/ROBUST-TAMP-authors/', location.origin);
  const pending = /\.github\.io$/.test(location.hostname);
  if (pending) root.classList.add('people-pending');
  const done = () => root.classList.remove('people-pending');
  setTimeout(done, 2500);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const withSup = (cls, text, sup) => { const s = el('span', cls, text); if (sup) s.append(el('sup', null, sup)); return s; };
  const safeUrl = u => { try { const x = new URL(u, base); return /^(https?:|mailto:)$/.test(x.protocol) ? x.href : null; } catch (e) { return null; } };

  function render(P) {
    const anon = document.querySelector('.anon');
    if (anon) {
      const box = el('div', 'people');
      const au = el('div', 'authors');
      P.authors.forEach(a => au.append(withSup(null, String(a.name), a.marks ? String(a.marks) : '')));
      box.append(au);
      if (Array.isArray(P.affiliations)) {
        const af = el('div', 'affils');
        P.affiliations.forEach(a => { const s = el('span'); s.append(el('sup', null, String(a.mark)), document.createTextNode(String(a.name))); af.append(s); });
        box.append(af);
      }
      const notes = el('div', 'corresp');
      if (P.equal_contribution) { const s = el('span'); s.append(el('sup', null, '†'), document.createTextNode(String(P.equal_contribution))); notes.append(s); }
      if (P.corresponding_email) {
        const s = el('span'); s.append(el('sup', null, '*'), document.createTextNode('Corresponding author: '));
        const a = el('a', null, String(P.corresponding_email)); a.href = 'mailto:' + String(P.corresponding_email); s.append(a); notes.append(s);
      }
      if (notes.childNodes.length) box.append(notes);
      if (Array.isArray(P.logos) && P.logos.length) {
        const lg = el('div', 'logos');
        P.logos.forEach(l => {
          const href = safeUrl(l.href), src = safeUrl(l.src); if (!src) return;
          const img = el('img'); img.src = src; img.alt = String(l.alt || ''); img.style.height = (Number(l.height) || 52) + 'px';
          if (href) { const a = el('a'); a.href = href; a.target = '_blank'; a.rel = 'noopener'; a.append(img); lg.append(a); } else lg.append(img);
        });
        box.append(lg);
      }
      anon.replaceWith(box);
    }
    const code = safeUrl(P.code_url);
    if (code) document.querySelectorAll('a.btn[href*="anonymous.4open.science"]').forEach(a => { a.href = code; });
    const bib = document.getElementById('bibtext');
    if (bib && P.bibtex_author) bib.textContent = bib.textContent.replace(/author\s*=\s*\{[^}]*\},\n/, `author = {${String(P.bibtex_author)}},\n`).replace(/,\n\s*note\s*=\s*\{[^}]*\}/, '');
    const foot = document.querySelector('footer .wrap');
    if (foot && P.footer) foot.textContent = String(P.footer);
  }

  fetch(new URL('authors.json', base), { cache: 'no-cache' })
    .then(r => (r.ok && /json/.test(r.headers.get('content-type') || '')) ? r.json() : null)
    .then(P => { if (P && P.version === 1 && Array.isArray(P.authors) && P.authors.length) render(P); })
    .catch(() => {})
    .then(done);
})();
