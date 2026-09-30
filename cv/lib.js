const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MarkdownIt = require('markdown-it');
const Md = MarkdownIt.default || MarkdownIt;
const md = new Md({ html: false, breaks: false, linkify: true });

// ---------------------------------------------------------------
// Text helpers
// ---------------------------------------------------------------
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function inlineToPlain(text) {
  return String(text)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .trim();
}

function parseContact(item) {
  const m = item.match(/^\*\*(.+?)\*\*\s*(.*)$/s);
  if (!m) return null;
  const key = m[1].replace(/:\s*$/, '').trim();
  let value = m[2].trim();
  let href = '';
  const lm = value.match(/^\[(.*?)\]\((.*?)\)$/);
  if (lm) {
    value = lm[1];
    href = lm[2];
  } else if (key.toLowerCase() === 'email') {
    href = 'mailto:' + value;
  } else if (key.toLowerCase() === 'cell') {
    href = 'tel:' + value.replace(/[^+\d]/g, '');
  }
  return { key, value, href };
}

function parseExperience(text) {
  const parts = text.split('\u2014'); // em dash
  const role = (parts[0] || '').trim();
  let org = '';
  let dates = '';
  if (parts[1]) {
    const rest = parts[1].trim();
    const m = rest.match(/^(.*?)\s*\(([^()]*)\)\s*$/);
    if (m) {
      org = m[1].trim();
      dates = m[2].trim();
    } else {
      org = rest;
    }
  }
  org = org.replace(/[*_]/g, '').trim();
  return { role, org, dates };
}

// ---------------------------------------------------------------
// Front matter: optional leading block of "key: value" lines
//   ---
//   lang: es
//   ---
// ---------------------------------------------------------------
function splitFrontMatter(text) {
  const src = String(text).replace(/^﻿/, '');
  const m = src.match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!m) return { meta: {}, body: src };
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$/);
    if (kv) meta[kv[1].toLowerCase()] = kv[2];
  }
  return { meta, body: src.slice(m[0].length) };
}

// ---------------------------------------------------------------
// i18n: rendered labels per language (cv/i18n.json).
// Language priority: CV_LANG env var > front matter "lang" > "en".
// ---------------------------------------------------------------
const I18N = JSON.parse(fs.readFileSync(path.join(__dirname, 'i18n.json'), 'utf8'));
const DEFAULT_LANG = 'en';

function resolveLang(meta) {
  const lang = (process.env.CV_LANG || (meta && meta.lang) || DEFAULT_LANG).trim().toLowerCase();
  if (!I18N[lang]) {
    console.error(`Language "${lang}" is not defined in cv/i18n.json. Available: ${Object.keys(I18N).join(', ')}.`);
    process.exit(1);
  }
  return lang;
}

// Label lookup with fallback to the default language.
function t(lang, key) {
  const get = (l) => key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), I18N[l]);
  const val = get(lang);
  if (val !== undefined) return val;
  console.warn(`Missing "${key}" for "${lang}" in cv/i18n.json; falling back to "${DEFAULT_LANG}".`);
  return get(DEFAULT_LANG);
}

// ---------------------------------------------------------------
// Markdown -> structured data (CV)
// ---------------------------------------------------------------
function parseMd(text) {
  const tokens = md.parse(splitFrontMatter(text).body, {});
  const data = { name: '', headline: '', contact: [], sections: [] };

  let section = null; // { heading, blocks }
  let inHeader = false;

  let i = 0;
  while (i < tokens.length) {
    const t = tokens[i];

    if (t.type === 'heading_open') {
      const inline = tokens[i + 1];
      const txt = inline ? inline.content.trim() : '';
      if (t.tag === 'h1') {
        data.name = txt;
        inHeader = true;
        section = null;
      } else if (t.tag === 'h2') {
        inHeader = false;
        section = { heading: txt, blocks: [] };
        data.sections.push(section);
      } else if (t.tag === 'h3') {
        if (section) section.blocks.push({ type: 'h3', text: txt });
      }
      i += 3;
      continue;
    }

    if (t.type === 'paragraph_open') {
      const inline = tokens[i + 1];
      const txt = inline ? inline.content.trim() : '';
      if (inHeader && !data.headline) {
        data.headline = txt;
      } else if (section) {
        section.blocks.push({ type: 'paragraph', text: txt });
      }
      i += 3;
      continue;
    }

    if (t.type === 'bullet_list_open') {
      const items = [];
      let j = i + 1;
      while (j < tokens.length && tokens[j].type !== 'bullet_list_close') {
        if (tokens[j].type === 'list_item_open') {
          let k = j + 1;
          while (k < tokens.length && tokens[k].type !== 'list_item_close') {
            if (tokens[k].type === 'inline') items.push(tokens[k].content.trim());
            k++;
          }
          j = k;
        }
        j++;
      }
      i = j + 1;

      if (inHeader) {
        for (const item of items) {
          const c = parseContact(item);
          if (c) data.contact.push(c);
        }
        inHeader = false;
      } else if (section) {
        section.blocks.push({ type: 'list', items });
      }
      continue;
    }

    i++;
  }

  return data;
}

// ---------------------------------------------------------------
// Shared header (name, headline, contact line) — CV and cover letter
// ---------------------------------------------------------------

// Standard labels recognised by parsers (contact keys come from the md).
const CONTACT_ORDER = ['location', 'cell', 'phone', 'email', 'linkedin', 'github'];

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

// ---------------------------------------------------------------
// Chrome discovery
// ---------------------------------------------------------------
function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ];
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  return null;
}

// ---------------------------------------------------------------
// Chrome render helpers
// ---------------------------------------------------------------
function runPdf(chrome, htmlPath, outPdf) {
  const args = [
    '--headless',
    '--disable-gpu',
    '--no-pdf-header-footer',
    `--print-to-pdf=${outPdf}`,
    htmlPath,
  ];
  return spawnSync(chrome, args, { encoding: 'utf8' });
}

function makeReporter(blockSelector) {
  const sel = JSON.stringify(blockSelector);
  return `
<script>
(function () {
  try {
    var page = document.querySelector('.page');
    if (!page) return;
    var blocks = document.querySelectorAll(${sel});
    var pr = page.getBoundingClientRect();
    var report = { totalOverflowPx: 0, blocks: [] };
    var overflow = page.scrollHeight - page.clientHeight;
    if (overflow > 0.5) report.totalOverflowPx = Math.round(overflow);
    var maxBottom = 0;
    blocks.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.bottom > maxBottom) maxBottom = r.bottom;
      var over = r.bottom - pr.bottom;
      if (over > 0.5) {
        var t = el.querySelector('.card__title');
        var name = t ? t.textContent.trim() : (el.className || '').split(' ')[0] || 'Block';
        report.blocks.push({ name: name, overflowPx: Math.round(over) });
      }
    });
    report.freePx = Math.round(pr.bottom - maxBottom);
    var pre = document.createElement('pre');
    pre.id = '__cv_overflow__';
    pre.textContent = btoa(unescape(encodeURIComponent(JSON.stringify(report))));
    document.body.appendChild(pre);
  } catch (e) {}
})();
<\/script>`;
}

function injectReporter(html, blockSelector) {
  return html.replace('</body>', makeReporter(blockSelector) + '</body>');
}

function measureOverflow(chrome, measurePath) {
  const args = [
    '--headless',
    '--disable-gpu',
    '--dump-dom',
    '--window-size=1200,1600',
    '--virtual-time-budget=1000',
    measurePath,
  ];
  const res = spawnSync(chrome, args, { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
  const dom = (res.stdout || '') + (res.stderr || '');
  const m = dom.match(/id="__cv_overflow__"[^>]*>([^<]+)</);
  if (!m) return null;
  try {
    const json = Buffer.from(m[1].trim(), 'base64').toString('utf8');
    return JSON.parse(json);
  } catch (e) {
    return null;
  }
}

function fillTemplate(template, fragments) {
  let out = template;
  for (const [key, value] of Object.entries(fragments)) {
    out = out.split('{{' + key + '}}').join(value);
  }
  return out;
}

module.exports = {
  md,
  esc,
  inlineToPlain,
  parseContact,
  parseExperience,
  splitFrontMatter,
  resolveLang,
  t,
  parseMd,
  renderHeader,
  findChrome,
  runPdf,
  makeReporter,
  injectReporter,
  measureOverflow,
  fillTemplate,
};
