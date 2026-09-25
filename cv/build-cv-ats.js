const fs = require('fs');
const path = require('path');
const lib = require('./lib');

const { md, esc, inlineToPlain, runPdf, fillTemplate } = lib;

// Resolve paths relative to this script.
const CV_DIR = __dirname;
const TEMPLATE_PATH = path.join(CV_DIR, 'design', 'template-ats.html');
const TMP_HTML = path.join(CV_DIR, 'design', '.tmp_cv_ats.html');

const MAX_PAGES = 2;

// ---------------------------------------------------------------
// Markdown section heading -> slot + standard ATS heading.
// Keys match the markdown contract used by build-cv.js.
// ---------------------------------------------------------------
const SECTIONS = {
  'Executive Profile': { slot: 'summary', title: 'Summary' },
  'Core Competencies & Technical Skills': { slot: 'skills', title: 'Skills' },
  'Professional Experience': { slot: 'experience', title: 'Professional Experience' },
  'Education & Certifications': { slot: 'education', title: 'Education & Certifications' },
  'Community Leadership & Tech Advocacy': { slot: 'community', title: 'Volunteer Experience' },
};

// Standard labels recognised by parsers (contact keys come from the md).
const CONTACT_ORDER = ['location', 'cell', 'phone', 'email', 'linkedin', 'github'];

// ---------------------------------------------------------------
// Render fragments (HTML strings) from structured data
// ---------------------------------------------------------------
function sectionTitle(text) {
  return `<h2 class="section__title">${esc(text)}</h2>`;
}

function bullets(items) {
  const lis = items.map((it) => `  <li>${md.renderInline(it)}</li>`).join('\n');
  return `<ul>\n${lis}\n</ul>`;
}

// Show the full URL as visible text so parsers capture it even without the link.
function visibleUrl(href) {
  return href.replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/+$/, '');
}

function renderHeader(data) {
  const name = esc(inlineToPlain(data.name));
  const headline = esc(inlineToPlain(data.headline));

  const contact = [...data.contact].sort((a, b) => {
    const ia = CONTACT_ORDER.indexOf(a.key.toLowerCase());
    const ib = CONTACT_ORDER.indexOf(b.key.toLowerCase());
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });

  const parts = contact.map((c) => {
    if (!c.href) return esc(c.value);
    const isWeb = /^https?:/i.test(c.href);
    const text = isWeb ? visibleUrl(c.href) : c.value;
    return `<a href="${esc(c.href)}">${esc(text)}</a>`;
  });

  return (
    `<h1 class="name">${name}</h1>\n` +
    `<p class="headline">${headline}</p>\n` +
    `<p class="contact">${parts.join(' | ')}</p>`
  );
}

function renderSummary(title, blocks) {
  const p = blocks.find((b) => b.type === 'paragraph');
  const text = p ? p.text : '';
  return `${sectionTitle(title)}\n<p class="summary">${md.renderInline(text)}</p>`;
}

function renderList(title, blocks) {
  const list = blocks.find((b) => b.type === 'list');
  const html = sectionTitle(title);
  return list ? html + '\n' + bullets(list.items) : html;
}

function renderJob(role, org, dates, items) {
  const meta = [org, dates].filter(Boolean).map(esc).join(' | ');
  let art = `<article class="job">\n`;
  art += `  <h3 class="job__role">${esc(role)}</h3>\n`;
  if (meta) art += `  <p class="job__meta">${meta}</p>\n`;
  if (items) art += bullets(items) + '\n';
  art += `</article>`;
  return art;
}

function renderExperience(title, blocks) {
  let html = sectionTitle(title);
  for (let b = 0; b < blocks.length; b++) {
    const blk = blocks[b];
    if (blk.type !== 'h3') continue;
    const { role, org, dates } = lib.parseExperience(blk.text);
    let items = null;
    if (blocks[b + 1] && blocks[b + 1].type === 'list') {
      items = blocks[b + 1].items;
      b++;
    }
    html += '\n\n' + renderJob(role, org, dates, items);
  }
  return html;
}

// Community subtitle follows "**Title | Org** (Dates)".
function renderCommunity(title, blocks) {
  const subtitle = blocks.find((b) => b.type === 'paragraph');
  const list = blocks.find((b) => b.type === 'list');
  let html = sectionTitle(title);

  if (!subtitle) {
    if (list) html += '\n' + bullets(list.items);
    return html;
  }

  let text = inlineToPlain(subtitle.text);
  let dates = '';
  const dm = text.match(/^(.*?)\s*\(([^()]*)\)\s*$/);
  if (dm) {
    text = dm[1].trim();
    dates = dm[2].trim();
  }
  const [role, ...rest] = text.split('|').map((s) => s.trim());
  html += '\n\n' + renderJob(role, rest.join(' | '), dates, list ? list.items : null);
  return html;
}

function renderSection(section) {
  const cfg = SECTIONS[section.heading];
  if (!cfg) return null;
  switch (cfg.slot) {
    case 'summary':
      return renderSummary(cfg.title, section.blocks);
    case 'skills':
    case 'education':
      return renderList(cfg.title, section.blocks);
    case 'experience':
      return renderExperience(cfg.title, section.blocks);
    case 'community':
      return renderCommunity(cfg.title, section.blocks);
    default:
      return null;
  }
}

// ---------------------------------------------------------------
// PDF helpers
// ---------------------------------------------------------------
function countPdfPages(pdfPath) {
  try {
    const buf = fs.readFileSync(pdfPath).toString('latin1');
    const pages = buf.match(/\/Type\s*\/Page(?![a-zA-Z])/g);
    if (pages && pages.length) return pages.length;
    const counts = [...buf.matchAll(/\/Count\s+(\d+)/g)].map((m) => Number(m[1]));
    return counts.length ? Math.max(...counts) : null;
  } catch (e) {
    return null;
  }
}

// ---------------------------------------------------------------
// Build: returns true when the ATS PDF was generated within limits.
// ---------------------------------------------------------------
function buildAts(data, mdPath, chrome) {
  const fragments = {
    TITLE: `${inlineToPlain(data.name)} — ${inlineToPlain(data.headline)}`,
    HEADER: renderHeader(data),
    SUMMARY: '',
    SKILLS: '',
    EXPERIENCE: '',
    EDUCATION: '',
    COMMUNITY: '',
  };

  for (const section of data.sections) {
    const cfg = SECTIONS[section.heading];
    if (cfg) fragments[cfg.slot.toUpperCase()] = renderSection(section);
  }

  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  const html = fillTemplate(template, fragments);
  fs.writeFileSync(TMP_HTML, html, 'utf8');

  const outPdf = mdPath.replace(/\.md$/i, '-ats.pdf');
  const res = runPdf(chrome, TMP_HTML, outPdf);

  if (process.env.CV_KEEP_HTML) {
    console.log('ATS HTML kept at ' + TMP_HTML);
  } else {
    fs.unlinkSync(TMP_HTML);
  }

  if (res.status !== 0) {
    console.error('Chrome failed (ATS):', res.stderr || res.stdout);
    return false;
  }

  console.log('OK -> ' + outPdf);

  const pages = countPdfPages(outPdf);
  if (pages === null) {
    console.warn('No se pudo contar las paginas del PDF ATS.');
    return true;
  }
  if (pages > MAX_PAGES) {
    console.warn(`ADVERTENCIA: el CV ATS ocupa ${pages} paginas (max. ${MAX_PAGES}). Acorta el markdown.`);
    return false;
  }
  console.log(`ATS: ${pages} pagina(s) (max. ${MAX_PAGES}).`);
  return true;
}

module.exports = { buildAts };
