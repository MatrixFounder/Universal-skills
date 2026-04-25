#!/usr/bin/env node
// Markdown outline → PPTX skeleton.
//
// `md2pptx.js` already handles full content, but for brainstorming
// you usually want to start from the table of contents — just the
// headings, with placeholder body text the editor fills in later.
// This script consumes a markdown file containing only `#`/`##`
// headings (and optional plain prose under each) and emits a deck
// where every heading becomes its own slide.
//
// Promotion rules (intentionally simple — keep this script small;
// for fancy layouts use md2pptx.js):
//   - `#`  → title slide (large heading, no bullets)
//   - `##` → content slide (heading + auto-bullet placeholder)
//   - `###`+ → demoted to bullets under the most-recent `##` slide
//   - prose paragraphs → become bullets under the current slide
//
// Usage:
//   node outline2pptx.js INPUT.md OUTPUT.pptx [--size 16:9|4:3]
//                                              [--theme theme.json]
//
// Output is a fully editable .pptx with one slide per heading and a
// "TODO: add content" placeholder under each `##`. Open in PowerPoint
// / Keynote / LibreOffice and flesh out the bullets.
"use strict";

const fs = require("fs");
const path = require("path");

const SCRIPT_DIR = __dirname;

function loadDependency(name) {
  try { return require(name); }
  catch (_) {
    try { return require(path.join(SCRIPT_DIR, "node_modules", name)); }
    catch (_) {
      console.error(`Missing dependency '${name}'. Run scripts/install.sh first.`);
      process.exit(1);
    }
  }
}

const pptxgen = loadDependency("pptxgenjs");

const DEFAULT_THEME = {
  bg: "FFFFFF",
  fg: "1F2937",
  muted: "6B7280",
  accent: "2563EB",
  accentLight: "DBEAFE",
  heading: { fontFace: "Calibri", fontSize: 32, color: "1F2937", bold: true },
  body:    { fontFace: "Calibri", fontSize: 18, color: "1F2937" },
};

function parseArgs(argv) {
  const out = { input: null, output: null, size: "16:9", themePath: null };
  const positionals = [];
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--size") out.size = argv[++i];
    else if (a === "--theme") out.themePath = argv[++i];
    else if (a === "--help" || a === "-h") return null;
    else if (a.startsWith("--")) throw new Error(`Unknown flag: ${a}`);
    else positionals.push(a);
  }
  if (positionals.length < 2) return null;
  out.input = positionals[0];
  out.output = positionals[1];
  return out;
}

function loadTheme(themePath) {
  if (!themePath) return DEFAULT_THEME;
  const raw = JSON.parse(fs.readFileSync(themePath, "utf-8"));
  return { ...DEFAULT_THEME, ...raw };
}

// Outline parser: walks the markdown line-by-line and groups content
// into slides. We treat `#` and `##` as slide separators; everything
// else becomes bullets (or sub-bullets) on the current slide. Code
// fences are passed through verbatim into a single bullet so the
// editor can spot them and decide whether to keep them.
function parseOutline(md) {
  const slides = [];
  let cur = null;
  let inFence = false;
  const flush = () => { if (cur) { slides.push(cur); cur = null; } };

  for (const rawLine of md.split(/\r?\n/)) {
    if (/^```/.test(rawLine)) {
      inFence = !inFence;
      if (cur) cur.bullets.push(rawLine);
      continue;
    }
    if (inFence) {
      if (cur) cur.bullets.push(rawLine);
      continue;
    }
    const h1 = rawLine.match(/^#\s+(.+?)\s*$/);
    const h2 = rawLine.match(/^##\s+(.+?)\s*$/);
    const h3 = rawLine.match(/^#{3,6}\s+(.+?)\s*$/);
    if (h1) {
      flush();
      cur = { kind: "title", title: h1[1], bullets: [] };
      continue;
    }
    if (h2) {
      flush();
      cur = { kind: "content", title: h2[1], bullets: [] };
      continue;
    }
    if (h3) {
      // Sub-heading → bold bullet on the current slide. Mark with a
      // sentinel object instead of `**foo**` text — pptxgenjs renders
      // strings verbatim (asterisks would show as literal characters);
      // the renderer below converts the sentinel to bullet options.
      if (cur) cur.bullets.push({ kind: "sub", text: h3[1] });
      continue;
    }
    const trimmed = rawLine.trim();
    if (!trimmed) continue;
    // Skip code-fence delimiters so a fenced block under a heading
    // doesn't show ``` lines as bullets in the skeleton output.
    if (/^```/.test(trimmed)) continue;
    // List item or bare paragraph → plain bullet
    const bullet = trimmed.replace(/^[-*]\s+/, "");
    if (cur) cur.bullets.push({ kind: "plain", text: bullet });
  }
  flush();
  return slides;
}

function makeTitleSlide(pres, theme, slide, title) {
  slide.background = { color: theme.bg };
  slide.addText(title, {
    x: 0.6, y: 2.4, w: 8.8, h: 1.5,
    fontFace: theme.heading.fontFace,
    fontSize: theme.heading.fontSize + 8,
    color: theme.heading.color,
    bold: theme.heading.bold,
    align: "center", valign: "middle",
  });
  // Accent stripe — visual cue this is a title, not a content slide
  slide.addShape(pres.ShapeType.rect, {
    x: 4.5, y: 4.0, w: 1.0, h: 0.05,
    fill: { color: theme.accent }, line: { type: "none" },
  });
}

function bulletToTextItem(bullet, theme) {
  // Sub-headings (`### ...` in the source) become BOLD bullets via
  // pptxgenjs' per-paragraph options — passing `**foo**` as a string
  // would render the asterisks as literal characters.
  if (bullet && bullet.kind === "sub") {
    return {
      text: bullet.text,
      options: { bullet: true, bold: true },
    };
  }
  // Plain bullets keep the default body styling.
  return {
    text: (bullet && bullet.text) || String(bullet || ""),
    options: { bullet: true },
  };
}

function makeContentSlide(pres, theme, slide, title, bullets) {
  slide.background = { color: theme.bg };
  // Accent stripe at top
  slide.addShape(pres.ShapeType.rect, {
    x: 0, y: 0, w: 10, h: 0.08,
    fill: { color: theme.accent }, line: { type: "none" },
  });
  slide.addText(title, {
    x: 0.5, y: 0.3, w: 9.0, h: 0.7,
    fontFace: theme.heading.fontFace,
    fontSize: theme.heading.fontSize,
    color: theme.heading.color,
    bold: theme.heading.bold,
  });

  // Body: editor-friendly placeholder when no bullets were captured,
  // so the slide doesn't look empty in PowerPoint.
  const items = bullets.length > 0
    ? bullets.map(b => bulletToTextItem(b, theme))
    : [{ text: "TODO: add content",
         options: { bullet: true, color: theme.muted, italic: true } }];

  slide.addText(items, {
    x: 0.6, y: 1.2, w: 8.8, h: 5.5,
    fontFace: theme.body.fontFace,
    fontSize: theme.body.fontSize,
    color: theme.body.color,
    valign: "top",
    paraSpaceAfter: 6,
  });
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args) {
    console.error(
      "Usage: node outline2pptx.js INPUT.md OUTPUT.pptx [--size 16:9|4:3] [--theme theme.json]"
    );
    process.exit(1);
  }
  if (!fs.existsSync(args.input)) {
    console.error(`Input not found: ${args.input}`);
    process.exit(1);
  }

  const md = fs.readFileSync(args.input, "utf-8");
  const theme = loadTheme(args.themePath);
  const slidesData = parseOutline(md);

  if (slidesData.length === 0) {
    console.error("No headings found in input. outline2pptx expects at least one `#` or `##` line.");
    process.exit(1);
  }

  const pres = new pptxgen();
  pres.layout = args.size === "4:3" ? "LAYOUT_4x3" : "LAYOUT_WIDE";
  pres.title = path.basename(args.input, ".md");

  for (const sd of slidesData) {
    const slide = pres.addSlide();
    if (sd.kind === "title") {
      makeTitleSlide(pres, theme, slide, sd.title);
    } else {
      makeContentSlide(pres, theme, slide, sd.title, sd.bullets);
    }
  }

  await pres.writeFile({ fileName: args.output });
  console.log(JSON.stringify({
    slides: slidesData.length,
    title_slides: slidesData.filter(s => s.kind === "title").length,
    content_slides: slidesData.filter(s => s.kind === "content").length,
    output: args.output,
  }, null, 2));
}

main().catch(err => {
  console.error(err.message || err);
  process.exit(1);
});
