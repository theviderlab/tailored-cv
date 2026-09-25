const fs = require('fs');
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
// Markdown -> structured data (CV)
// ---------------------------------------------------------------
function parseMd(text) {
  const tokens = md.parse(text, {});
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
  parseMd,
  findChrome,
  runPdf,
  makeReporter,
  injectReporter,
  measureOverflow,
  fillTemplate,
};
