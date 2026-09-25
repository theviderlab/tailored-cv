const fs = require('fs');
const path = require('path');
const lib = require('./lib');
const { buildAts } = require('./build-cv-ats');

const { md, esc, inlineToPlain, parseMd, findChrome, runPdf, injectReporter, measureOverflow, fillTemplate } = lib;

// Resolve paths relative to this script.
const CV_DIR = __dirname;
const TEMPLATE_PATH = path.join(CV_DIR, 'design', 'template.html');
const TMP_HTML = path.join(CV_DIR, 'design', '.tmp_cv.html');
const TMP_MEASURE_HTML = path.join(CV_DIR, 'design', '.tmp_measure.html');

// ---------------------------------------------------------------
// Section heading -> card slot
// ---------------------------------------------------------------
const SECTION_SLOTS = {
  'Executive Profile': 'profile',
  'Core Competencies & Technical Skills': 'skills',
  'Professional Experience': 'experience',
  'Community Leadership & Tech Advocacy': 'community',
  'Education & Certifications': 'education',
};

// ---------------------------------------------------------------
// Render fragments (HTML strings) from structured data
// ---------------------------------------------------------------
function cardTitle(text) {
  return `<h2 class="card__title">${esc(text)}</h2>`;
}

function bullets(items) {
  const lis = items.map((it) => `  <li>${md.renderInline(it)}</li>`).join('\n');
  return `<ul class="bullets">\n${lis}\n</ul>`;
}

function renderHeader(data) {
  const name = esc(data.name);
  const headline = esc(inlineToPlain(data.headline));
  const contact = data.contact
    .map((c) => {
      const val = c.href ? `<a href="${esc(c.href)}">${esc(c.value)}</a>` : esc(c.value);
      return `    <dt>${esc(c.key)}:</dt>\n    <dd>${val}</dd>`;
    })
    .join('\n');
  return `<h1 class="name">${name}</h1>\n<p class="headline">${headline}</p>\n<dl class="contact">\n${contact}\n</dl>`;
}

function renderProfile(blocks) {
  const p = blocks.find((b) => b.type === 'paragraph');
  const text = p ? p.text : '';
  return `<h2 class="card__title">${esc('Executive Profile')}</h2>\n<p class="profile">${md.renderInline(text)}</p>`;
}

function renderSkills(blocks) {
  const list = blocks.find((b) => b.type === 'list');
  const html = cardTitle('Core Competencies & Technical Skills');
  return list ? html + '\n' + bullets(list.items) : html;
}

function renderEducation(blocks) {
  const list = blocks.find((b) => b.type === 'list');
  let html = cardTitle('Education & Certifications');
  if (list) {
    const ps = list.items.map((it) => `  <p>${md.renderInline(it)}</p>`).join('\n');
    html += `\n<div class="edu">\n${ps}\n</div>`;
  }
  return html;
}

function renderCommunity(blocks) {
  const subtitle = blocks.find((b) => b.type === 'paragraph');
  const list = blocks.find((b) => b.type === 'list');
  let html = cardTitle('Community Leadership & Tech Advocacy');
  if (subtitle) {
    html += `\n<p class="job__org">${esc(inlineToPlain(subtitle.text))}</p>`;
  }
  if (list) html += '\n' + bullets(list.items);
  return html;
}

function renderExperience(blocks) {
  let html = cardTitle('Professional Experience');
  for (let b = 0; b < blocks.length; b++) {
    const blk = blocks[b];
    if (blk.type !== 'h3') continue;
    const { role, org, dates } = lib.parseExperience(blk.text);
    let art = `<article class="job">\n`;
    art += `  <h3 class="job__role">${esc(role)}${dates ? ` (${esc(dates)})` : ''}</h3>\n`;
    if (org) art += `  <p class="job__org">${esc(org)}</p>\n`;
    if (blocks[b + 1] && blocks[b + 1].type === 'list') {
      art += bullets(blocks[b + 1].items);
      b++;
    }
    art += `</article>`;
    html += '\n\n' + art;
  }
  return html;
}

function renderSection(section) {
  const slot = SECTION_SLOTS[section.heading];
  if (!slot) return null;
  switch (slot) {
    case 'profile':
      return renderProfile(section.blocks);
    case 'skills':
      return renderSkills(section.blocks);
    case 'education':
      return renderEducation(section.blocks);
    case 'community':
      return renderCommunity(section.blocks);
    case 'experience':
      return renderExperience(section.blocks);
    default:
      return null;
  }
}

// ---------------------------------------------------------------
// Main
// ---------------------------------------------------------------
function main() {
  const input = process.argv[2];
  if (!input) {
    console.error('Usage: npm run cv -- <path-to-md>');
    process.exit(1);
  }

  const mdPath = path.resolve(input);
  if (!fs.existsSync(mdPath)) {
    console.error('File not found: ' + mdPath);
    process.exit(1);
  }

  const mdText = fs.readFileSync(mdPath, 'utf8');
  const data = parseMd(mdText);

  const fragments = {
    TITLE: `${inlineToPlain(data.name)} — ${inlineToPlain(data.headline)}`,
    HEADER: renderHeader(data),
  };

  const slots = { profile: '', skills: '', education: '', community: '', experience: '' };
  for (const section of data.sections) {
    const slot = SECTION_SLOTS[section.heading];
    if (slot) slots[slot] = renderSection(section);
  }
  fragments.PROFILE = slots.profile;
  fragments.SKILLS = slots.skills;
  fragments.EDUCATION = slots.education;
  fragments.COMMUNITY = slots.community;
  fragments.EXPERIENCE = slots.experience;

  const template = fs.readFileSync(TEMPLATE_PATH, 'utf8');
  const html = fillTemplate(template, fragments);

  fs.writeFileSync(TMP_HTML, html, 'utf8');
  fs.writeFileSync(TMP_MEASURE_HTML, injectReporter(html, '.card'), 'utf8');

  const chrome = findChrome();
  if (!chrome) {
    console.error('Chrome/Edge not found. Set CHROME_PATH env var.');
    process.exit(1);
  }

  const outPdf = mdPath.replace(/\.md$/i, '.pdf');
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

  // ATS-optimized variant from the same parsed markdown.
  const atsOk = buildAts(data, mdPath, chrome);

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
    console.warn('ADVERTENCIA: hay bloques que no entran en una pagina. Acorta el markdown.');
    process.exit(1);
  } else if (report && report.freePx !== undefined) {
    console.log('Headroom: ' + report.freePx + 'px libres en la pagina.');
  }

  if (!atsOk) process.exit(1);
}

main();
