const fs = require('fs');
const path = require('path');
const lib = require('./lib');

const { md, esc, inlineToPlain, parseMd, findChrome, runPdf, injectReporter, measureOverflow, fillTemplate } = lib;

// Resolve paths relative to this script.
const CV_DIR = __dirname;
const TEMPLATE_PATH = path.join(CV_DIR, 'design', 'template-cover-letter.html');
const TMP_HTML = path.join(CV_DIR, 'design', '.tmp_cover.html');
const TMP_MEASURE_HTML = path.join(CV_DIR, 'design', '.tmp_measure_cover.html');

const DEFAULT_CV_BASE = path.resolve(__dirname, '..', 'workspace', 'cv-base.md');
const BLOCK_SELECTOR = '.letterhead, .letter, .signature';

const ICON_MAP = {
  email: 'email',
  cell: 'phone',
  linkedin: 'linkedin',
  github: 'web',
  location: 'location',
};

// ---------------------------------------------------------------
// Cover letter markdown -> structured data
//
// Convention (blocks separated by blank lines):
//   1st block  = salutation ("Dear Hiring Team,")
//   last block = closing: first line = signoff ("Best regards,"),
//                remaining lines = signature (name)
//   everything between = body paragraphs
// ---------------------------------------------------------------
function parseCoverLetter(text) {
  const blocks = text
    .replace(/\r\n?/g, '\n')
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean);

  if (blocks.length === 0) return { salutation: '', signoff: '', signature: '', body: [] };

  const salutation = blocks[0];

  const closing = blocks[blocks.length - 1]
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  let signoff = '';
  let signature = '';
  if (closing.length === 1) {
    signature = closing[0];
  } else {
    signoff = closing[0];
    signature = closing.slice(1).join(' ');
  }

  const body = blocks.slice(1, blocks.length - 1);
  return { salutation, signoff, signature, body };
}

// ---------------------------------------------------------------
// Render fragments
// ---------------------------------------------------------------
function renderContact(contact) {
  const items = contact
    .map((c) => {
      const icon = ICON_MAP[c.key.toLowerCase()] || 'web';
      const inner = c.href ? `<a href="${esc(c.href)}">${esc(c.value)}</a>` : esc(c.value);
      return `  <li data-icon="${icon}">${inner}</li>`;
    })
    .join('\n');
  return `<ul class="contact">\n${items}\n</ul>`;
}

function renderBody(p) {
  const parts = [];
  if (p.salutation) parts.push(`<p class="salutation">${md.renderInline(p.salutation)}</p>`);
  for (const para of p.body) parts.push(`<p>${md.renderInline(para)}</p>`);
  if (p.signoff) parts.push(`<p class="signoff">${md.renderInline(p.signoff)}</p>`);
  return parts.join('\n');
}

// ---------------------------------------------------------------
// Main
// ---------------------------------------------------------------
function main() {
  const input = process.argv[2];
  if (!input) {
    console.error('Usage: npm run cover -- <cover-letter.md> [cv-base.md]');
    process.exit(1);
  }

  const letterPath = path.resolve(input);
  if (!fs.existsSync(letterPath)) {
    console.error('File not found: ' + letterPath);
    process.exit(1);
  }

  const cvBasePath = process.argv[3]
    ? path.resolve(process.argv[3])
    : process.env.CV_BASE
      ? path.resolve(process.env.CV_BASE)
      : DEFAULT_CV_BASE;
  if (!fs.existsSync(cvBasePath)) {
    console.error('CV base not found: ' + cvBasePath);
    process.exit(1);
  }

  const cvData = parseMd(fs.readFileSync(cvBasePath, 'utf8'));
  const letter = parseCoverLetter(fs.readFileSync(letterPath, 'utf8'));

  const fragments = {
    TITLE: `${inlineToPlain(cvData.name)} — Cover Letter`,
    NAME: esc(cvData.name),
    HEADLINE: esc(inlineToPlain(cvData.headline)),
    CONTACT: renderContact(cvData.contact),
    BODY: renderBody(letter),
    SIGNATURE: esc(letter.signature),
  };

  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  const html = fillTemplate(template, fragments);

  fs.writeFileSync(TMP_HTML, html, 'utf8');
  fs.writeFileSync(TMP_MEASURE_HTML, injectReporter(html, BLOCK_SELECTOR), 'utf8');

  const chrome = findChrome();
  if (!chrome) {
    console.error('Chrome/Edge not found. Set CHROME_PATH env var.');
    process.exit(1);
  }

  const outPdf = letterPath.replace(/\.md$/i, '.pdf');
  const report = measureOverflow(chrome, TMP_MEASURE_HTML);
  const res = runPdf(chrome, TMP_HTML, outPdf);

  if (process.env.CV_KEEP_HTML) {
    console.log('HTML kept at ' + TMP_HTML);
  } else {
    fs.unlinkSync(TMP_HTML);
    fs.unlinkSync(TMP_MEASURE_HTML);
  }

  if (res.status !== 0) {
    console.error('Chrome failed:', res.stderr || res.stdout);
    process.exit(res.status || 1);
  }

  console.log('OK -> ' + outPdf);

  let overflow = false;
  if (report) {
    if (report.totalOverflowPx > 0) {
      overflow = true;
      console.warn('OVERFLOW: el contenido excede una pagina por ' + report.totalOverflowPx + 'px.');
    }
    for (const b of report.blocks) {
      overflow = true;
      console.warn('  - bloque "' + b.name + '" se desborda por ' + b.overflowPx + 'px.');
    }
  } else {
    console.warn('No se pudo medir el overflow (Chrome no devolvio el reporte).');
  }

  if (overflow) {
    console.warn('ADVERTENCIA: hay bloques que no entran en una pagina. Acorta la carta.');
    process.exit(1);
  } else if (report && report.freePx !== undefined) {
    console.log('Headroom: ' + report.freePx + 'px libres en la pagina.');
  }
}

main();
