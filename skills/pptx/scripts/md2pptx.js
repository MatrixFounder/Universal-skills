#!/usr/bin/env node
/**
 * md2pptx.js — Markdown → .pptx converter built on pptxgenjs.
 *
 * Accepts a Markdown document split into slides by `---` lines (a
 * standalone horizontal rule). Each slide's first heading is treated
 * as the title; a second-level heading directly after is the
 * subtitle. Subsequent content becomes the body.
 *
 * Supported body constructs:
 *   - paragraphs (mapped to a text block)
 *   - bulleted / numbered lists
 *   - fenced code blocks (monospace text box with light fill)
 *   - block quotes (italic, accent colour)
 *   - GFM tables
 *   - images (`![alt](path)`) — local path relative to the .md file
 *
 * Aspect ratio: 16:9 by default (10 × 5.625 inches). Pass `--size 4:3`
 * for 10 × 7.5 inches.
 *
 * Usage:
 *   node md2pptx.js INPUT.md OUTPUT.pptx [--size 16:9|4:3] [--theme PATH]
 *
 * Exit codes:
 *   0  success
 *   1  bad args / missing input / pptxgenjs failure
 */

"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");
const crypto = require("crypto");
const { execSync } = require("child_process");
const marked = require("marked");
const pptxgen = require("pptxgenjs");

let _imageSize = null;
function getImageSize(filePath) {
  if (_imageSize === null) {
    try { _imageSize = require("image-size"); } catch (e) { _imageSize = false; }
  }
  if (!_imageSize) return null;
  try {
    const fn = _imageSize.imageSize || _imageSize.default || _imageSize;
    return fn(fs.readFileSync(filePath));
  } catch (e) { return null; }
}

// Mermaid renderer is optional — when `mmdc` (@mermaid-js/mermaid-cli)
// is present, fenced ```mermaid blocks become embedded PNGs; otherwise
// they fall back to code-block rendering with a clear notice.
const MERMAID_CACHE_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "md2pptx-mermaid-"));

function resolveMmdc() {
  const localBin = path.resolve(__dirname, "node_modules", ".bin", "mmdc");
  if (fs.existsSync(localBin)) return localBin;
  try {
    const found = execSync("command -v mmdc", { encoding: "utf-8" }).trim();
    if (found) return found;
  } catch (e) { /* fall through */ }
  return null;
}

let _mmdc = undefined;
function mmdcPath() {
  if (_mmdc === undefined) _mmdc = resolveMmdc();
  return _mmdc;
}
function hasMermaid() { return !!mmdcPath(); }

function renderMermaid(source) {
  const bin = mmdcPath();
  if (!bin) return null;
  const hash = crypto.createHash("sha1").update(source).digest("hex").slice(0, 12);
  const mmdFile = path.join(MERMAID_CACHE_DIR, `${hash}.mmd`);
  const pngFile = path.join(MERMAID_CACHE_DIR, `${hash}.png`);
  if (fs.existsSync(pngFile)) return pngFile;
  fs.writeFileSync(mmdFile, source);
  try {
    execSync(`"${bin}" -i "${mmdFile}" -o "${pngFile}" -s 2 -b white -t neutral`,
             { stdio: "ignore" });
    return fs.existsSync(pngFile) ? pngFile : null;
  } catch (e) {
    return null;
  }
}

const DEFAULT_THEME = {
  name: "Charcoal Minimal",
  bg: "FFFFFF",
  fg: "1F2937",
  muted: "6B7280",
  accent: "2563EB",
  accentLight: "DBEAFE",
  heading: { fontFace: "Calibri", fontSize: 30, color: "1F2937", bold: true },
  subheading: { fontFace: "Calibri", fontSize: 18, color: "6B7280" },
  body: { fontFace: "Calibri", fontSize: 15, color: "1F2937" },
  code: { fontFace: "Menlo", fontSize: 12, color: "1F2937", fill: "F3F4F6" },
  quote: { fontFace: "Calibri", fontSize: 17, color: "2563EB", italic: true },
  caption: { fontFace: "Calibri", fontSize: 11, color: "6B7280", italic: true },
};

// Base body font size; actual size is adapted per-slide by `scaleFontSizes`.
const BODY_FONT_BASE = 15;
const BODY_FONT_MIN = 11;

function parseArgs(argv) {
  const out = {
    input: null, output: null, size: "16:9",
    themePath: null,
    viaMarp: false,
    marpTheme: null,
  };
  const positionals = [];
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--size") out.size = argv[++i];
    else if (a === "--theme") out.themePath = argv[++i];
    else if (a === "--via-marp") out.viaMarp = true;
    else if (a === "--marp-theme") out.marpTheme = argv[++i];
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

function splitSlides(source) {
  const lines = source.split(/\r?\n/);
  const slides = [];
  let current = [];
  let inFence = false;
  for (const line of lines) {
    if (/^```/.test(line)) inFence = !inFence;
    if (!inFence && /^---\s*$/.test(line) && current.length > 0) {
      slides.push(current.join("\n"));
      current = [];
      continue;
    }
    current.push(line);
  }
  if (current.length > 0) slides.push(current.join("\n"));
  return slides.map(s => s.trim()).filter(s => s.length > 0);
}

const MAX_BULLETS_PER_CHUNK = 5;
const LINE_H = 0.32;      // body text line height at 16pt (generous for Cyrillic)
const GAP = 0.2;          // vertical gap between blocks
const BLOCK_PAD = 0.25;   // top/bottom padding inside a text box
const MERMAID_H = 3.8;    // visual height reserved for a mermaid image
const MERMAID_W = 7.0;

function listItemText(item) {
  // For "loose" lists marked emits items with embedded paragraph tokens
  // whose text carries leading/trailing newlines. If we feed that to
  // pptxgenjs unchanged, each bullet renders with phantom blank lines
  // and the numbering looks doubled. Flatten to single-line per bullet.
  const raw = (item && (item.text || "")) || "";
  return raw.replace(/\s*\n+\s*/g, " ").trim();
}

function tokenHeight(tok, w) {
  if (tok.type === "paragraph") {
    return BLOCK_PAD + LINE_H * estimateLines(tok.text || "", w) + GAP;
  }
  if (tok.type === "list") {
    const items = tok.items || [];
    // Each bullet: at least one line; wrap long ones to extra lines.
    let lines = 0;
    for (const it of items) {
      lines += estimateLines(listItemText(it), w - 0.35);
    }
    return BLOCK_PAD + LINE_H * Math.max(lines, items.length) + GAP;
  }
  if (tok.type === "code") {
    if (tok.lang === "mermaid") return MERMAID_H + GAP;
    const lines = (tok.text || "").split("\n").length;
    return BLOCK_PAD + 0.22 * lines + GAP;
  }
  if (tok.type === "blockquote") {
    const txt = (tok.tokens || []).map(t => t.text || "").join(" ");
    return BLOCK_PAD + LINE_H * estimateLines(txt, w - 0.3) + GAP;
  }
  if (tok.type === "table") {
    const rows = (tok.rows || []).length + 1;
    return BLOCK_PAD + 0.36 * rows + GAP;
  }
  if (tok.type === "heading") return 0.55;
  if (tok.type === "html") return 0;
  return 0;
}

function estimateTokenHeight(tok, w) { return tokenHeight(tok, w); }

function splitList(listTok, maxPerChunk) {
  const chunks = [];
  const items = listTok.items || [];
  for (let i = 0; i < items.length; i += maxPerChunk) {
    chunks.push({ ...listTok, items: items.slice(i, i + maxPerChunk) });
  }
  return chunks;
}

function expandOversizedBlocks(body) {
  const out = [];
  for (const tok of body) {
    if (tok.type === "list" && (tok.items || []).length > MAX_BULLETS_PER_CHUNK) {
      for (const chunk of splitList(tok, MAX_BULLETS_PER_CHUNK)) out.push(chunk);
    } else {
      out.push(tok);
    }
  }
  return out;
}

function paginateBody(body, maxY, contentWidth) {
  const expanded = expandOversizedBlocks(body);
  const pages = [];
  let current = [];
  let used = 0;
  for (const tok of expanded) {
    const h = estimateTokenHeight(tok, contentWidth);
    if (used + h > maxY && current.length > 0) {
      pages.push(current);
      current = [tok];
      used = h;
    } else {
      current.push(tok);
      used += h;
    }
  }
  if (current.length > 0) pages.push(current);
  return pages.length > 0 ? pages : [[]];
}

function countContentChars(tokens) {
  let n = 0;
  for (const t of tokens || []) {
    if (t.type === "paragraph") n += (t.text || "").length;
    else if (t.type === "list") {
      for (const it of (t.items || [])) n += (it.text || "").length;
    } else if (t.type === "code") n += (t.text || "").length;
    else if (t.type === "blockquote") {
      for (const tt of (t.tokens || [])) n += (tt.text || "").length;
    } else if (t.type === "table") {
      for (const row of (t.rows || [])) for (const c of row) n += (c.text || "").length;
    }
  }
  return n;
}

function scaledTheme(theme, tokens) {
  // Dense slides get a smaller body font so text fits without
  // overflowing. Thresholds are empirical: 800 chars ~ normal, 1500+
  // starts to pack, we go down toward BODY_FONT_MIN.
  const chars = countContentChars(tokens);
  const extra = Math.min(4, Math.floor(Math.max(0, chars - 800) / 200));
  const bodySize = Math.max(BODY_FONT_MIN, BODY_FONT_BASE - extra);
  return {
    ...theme,
    body: { ...theme.body, fontSize: bodySize },
    code: { ...theme.code, fontSize: Math.max(10, bodySize - 3) },
    quote: { ...theme.quote, fontSize: Math.max(13, bodySize + 1) },
  };
}

function drawAccentStripe(slide, theme, pageLayout) {
  // Thin vertical bar on the left of every slide — a cheap but
  // effective way to give every slide a recognisable visual anchor.
  slide.addShape("rect", {
    x: 0, y: 0, w: 0.16, h: pageLayout.slideH,
    fill: { color: theme.accent },
    line: { type: "none" },
  });
}

function pickHeadingSize(title, baseSize) {
  // Long titles need a smaller font to fit on one or two lines.
  // Empirical scaling for ~8.0" wide title area at the chosen face.
  if (!title) return baseSize;
  const len = title.length;
  if (len <= 50) return baseSize;
  if (len <= 80) return Math.max(22, baseSize - 4);
  if (len <= 120) return Math.max(20, baseSize - 8);
  return Math.max(18, baseSize - 12);
}

function estimateTitleHeight(title, fontSize, widthInches) {
  if (!title) return 0;
  // Heading wraps at ~ widthInches * (0.7 chars/pt * 16/fontSize). Give
  // ~1.25× line-height to fit cyrillic descenders/ascenders.
  const charsPerLine = Math.max(20, Math.floor(widthInches * 7 * (16 / fontSize)));
  const lines = Math.max(1, Math.ceil(title.length / charsPerLine));
  return Math.min(2.2, lines * (fontSize / 72) * 1.45 + 0.1);
}

function estimateSubtitleHeight(subtitle, fontSize, widthInches) {
  if (!subtitle) return 0;
  // Subtitle is typically shorter and italic; use the same wrap math as
  // the title but with a tighter line-multiplier (1.35 vs 1.45) and no
  // ceiling — long metadata lines ("Date | Duration | Speaker") should
  // not force a second line unless they genuinely don't fit.
  const charsPerLine = Math.max(20, Math.floor(widthInches * 7 * (16 / fontSize)));
  const lines = Math.max(1, Math.ceil(subtitle.length / charsPerLine));
  return Math.min(1.5, lines * (fontSize / 72) * 1.35 + 0.08);
}

function renderOnePage(pres, baseTheme, title, subtitle, pageTokens, pageLabel, pageLayout) {
  const theme = scaledTheme(baseTheme, pageTokens);
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  drawAccentStripe(slide, theme, pageLayout);

  const contentLeft = 0.55;
  const contentWidth = 8.9;
  let y = 0.4;

  if (title) {
    const titleW = contentWidth - 1.2;
    const titleSize = pickHeadingSize(title, theme.heading.fontSize);
    const titleH = estimateTitleHeight(title, titleSize, titleW);
    slide.addText(title, {
      x: contentLeft, y, w: titleW, h: titleH,
      ...theme.heading,
      fontSize: titleSize,
      color: theme.accent,
      fit: "shrink",
      valign: "top",
    });
    if (pageLabel) {
      slide.addText(pageLabel, {
        x: contentLeft + contentWidth - 1.15, y: y + 0.15, w: 1.1, h: 0.5,
        fontFace: theme.subheading.fontFace,
        fontSize: 12,
        color: theme.muted,
        align: "right",
      });
    }
    y += titleH + 0.05;
    // Thin underline under the title for additional visual structure.
    slide.addShape("rect", {
      x: contentLeft, y: y - 0.04, w: 0.6, h: 0.04,
      fill: { color: theme.accent }, line: { type: "none" },
    });
    y += 0.08;
  }
  if (subtitle) {
    const subH = estimateSubtitleHeight(subtitle, theme.subheading.fontSize, contentWidth);
    slide.addText(subtitle, {
      x: contentLeft, y, w: contentWidth, h: subH,
      ...theme.subheading,
      fit: "shrink",
      valign: "top",
    });
    y += subH + 0.1;
  }

  const slideMaxY = pageLayout.slideH - 0.4;
  let skipped = 0;
  for (const tok of pageTokens) {
    if (y > slideMaxY) {
      skipped++;
      continue;
    }
    y = renderToken(slide, tok, y, contentLeft, contentWidth, theme, null);
  }
  return skipped;
}

function renderSlide(pres, md, theme, slideIndex, pageLayout) {
  const tokens = marked.lexer(md);

  // Strip standalone `hr` tokens — they carry no content.
  const significant = tokens.filter(t => t.type !== "space" && t.type !== "hr");
  if (significant.length === 0) {
    console.error(`Warning: slide ${slideIndex} contained no renderable content, skipping`);
    return { rendered: 0, paginated: 0, skipped: 0 };
  }

  let title = null;
  let subtitle = null;
  const body = [];

  for (const tok of significant) {
    if (tok.type === "heading" && tok.depth === 1 && title === null) {
      title = tok.text;
    } else if (tok.type === "heading" && tok.depth === 2 && subtitle === null && title !== null && body.length === 0) {
      subtitle = tok.text;
    } else {
      body.push(tok);
    }
  }

  // Body budget = slide height − dynamic title − dynamic subtitle − bottom margin.
  // Both heights depend on text length (long titles wrap to 2-3 lines;
  // long metadata subtitles can wrap too).
  const titleSize = pickHeadingSize(title, theme.heading.fontSize);
  const titleH = title ? estimateTitleHeight(title, titleSize, 7.7) + 0.13 : 0;
  const subH = subtitle ? estimateSubtitleHeight(subtitle, theme.subheading.fontSize, 8.9) + 0.1 : 0;
  const bodyBudget = pageLayout.slideH - 0.4 - titleH - subH - 0.4;
  const pages = paginateBody(body, bodyBudget, 8.9);

  let totalSkipped = 0;
  for (let p = 0; p < pages.length; p++) {
    const pageLabel = pages.length > 1 ? `${p + 1} / ${pages.length}` : null;
    totalSkipped += renderOnePage(pres, theme, title, subtitle, pages[p], pageLabel, pageLayout);
  }

  if (pages.length > 1) {
    console.error(
      `Note: slide ${slideIndex} ("${title || "untitled"}") auto-paginated into ${pages.length} slides.`
    );
  }
  return { rendered: pages.length, paginated: pages.length > 1 ? 1 : 0, skipped: totalSkipped };
}

function renderToken(slide, tok, y, x, w, theme, slideMd) {
  const h = tokenHeight(tok, w);
  const innerH = Math.max(0.4, h - GAP);

  if (tok.type === "paragraph") {
    slide.addText(inlineToText(tok.tokens, theme), {
      x, y, w, h: innerH, valign: "top", fit: "shrink", ...theme.body,
    });
    return y + h;
  }
  if (tok.type === "list") {
    const bulletType = tok.ordered ? { type: "number" } : { type: "bullet" };
    const items = (tok.items || []).map(item => ({
      text: listItemText(item),
      options: { bullet: bulletType, indentLevel: 0, paraSpaceAfter: 2 },
    }));
    slide.addText(items, {
      x, y, w, h: innerH, valign: "top",
      lineSpacingMultiple: 1.1, fit: "shrink",
      ...theme.body,
    });
    return y + h;
  }
  if (tok.type === "code" && tok.lang === "mermaid") {
    let pngPath = null;
    if (hasMermaid()) pngPath = renderMermaid(tok.text || "");
    if (pngPath) {
      const captionH = 0.22;
      const boxW = w - 0.4;
      const boxH = Math.max(0.8, innerH - captionH - 0.05);
      // Read native PNG dimensions and fit-into the box preserving
      // aspect ratio. pptxgenjs `sizing: contain` doesn't work reliably
      // when the box ratio differs from the image, so we compute the
      // final w/h ourselves.
      const dims = getImageSize(pngPath);
      let finalW = boxW;
      let finalH = boxH;
      if (dims && dims.width && dims.height) {
        const scale = Math.min(boxW / dims.width, boxH / dims.height);
        finalW = dims.width * scale;
        finalH = dims.height * scale;
      }
      const imgX = x + (w - finalW) / 2;
      const imgY = y + (boxH - finalH) / 2;
      // Light border behind the image for structure.
      slide.addShape("rect", {
        x: x + (w - boxW) / 2 - 0.06, y: y - 0.04,
        w: boxW + 0.12, h: boxH + 0.08,
        fill: { color: "FAFAFA" },
        line: { type: "solid", color: "E5E7EB", pt: 0.5 },
      });
      slide.addImage({ path: pngPath, x: imgX, y: imgY, w: finalW, h: finalH });
      slide.addText("Diagram", {
        x, y: y + boxH + 0.05, w, h: captionH,
        align: "center", ...theme.caption,
      });
      return y + h;
    }
    const note = `[mermaid — install @mermaid-js/mermaid-cli to render]\n${tok.text || ""}`;
    slide.addText(note, {
      x, y, w, h: innerH,
      fill: { color: theme.code.fill },
      fontFace: theme.code.fontFace, fontSize: theme.code.fontSize,
      color: theme.code.color, valign: "top", margin: 0.08, fit: "shrink",
    });
    return y + h;
  }
  if (tok.type === "code") {
    slide.addText(tok.text || "", {
      x, y, w, h: innerH,
      fill: { color: theme.code.fill },
      fontFace: theme.code.fontFace, fontSize: theme.code.fontSize,
      color: theme.code.color, valign: "top", margin: 0.08, fit: "shrink",
    });
    return y + h;
  }
  if (tok.type === "blockquote") {
    const txt = (tok.tokens || []).map(t => t.text || "").join(" ");
    // Left accent line for quote
    slide.addShape("rect", {
      x, y, w: 0.04, h: innerH,
      fill: { color: theme.accent }, line: { type: "none" },
    });
    slide.addText(txt, {
      x: x + 0.2, y, w: w - 0.2, h: innerH,
      valign: "top", fit: "shrink", ...theme.quote,
    });
    return y + h;
  }
  if (tok.type === "table") {
    const header = (tok.header || []).map(hh => ({
      text: hh.text,
      options: { bold: true, fill: theme.accentLight, color: theme.fg },
    }));
    const rows = [header, ...(tok.rows || []).map(r => r.map(c => ({ text: c.text })))];
    slide.addTable(rows, {
      x, y, w, h: innerH,
      fontFace: theme.body.fontFace,
      fontSize: Math.max(10, theme.body.fontSize - 2),
      color: theme.body.color,
      border: { type: "solid", color: "E5E7EB", pt: 0.5 },
      autoPage: false,
    });
    return y + h;
  }
  if (tok.type === "html") return y;
  return y;
}

function inlineToText(tokens, theme) {
  if (!tokens) return [];
  const out = [];
  for (const t of tokens) {
    if (t.type === "text") out.push({ text: t.text });
    else if (t.type === "strong") out.push({ text: t.text, options: { bold: true } });
    else if (t.type === "em") out.push({ text: t.text, options: { italic: true } });
    else if (t.type === "codespan") out.push({ text: t.text, options: { fontFace: theme.code.fontFace } });
    else if (t.type === "link") out.push({ text: t.text, options: { hyperlink: { url: t.href }, color: theme.accent } });
    else if (t.text) out.push({ text: t.text });
  }
  return out;
}

function estimateLines(text, widthInches) {
  // Char-width heuristic at 16pt body. Cyrillic (and some CJK) glyphs
  // run wider than Latin, so we use a conservative ~5.5 chars/inch —
  // slightly overestimates lines for English text, but prevents the
  // classic overlap-on-Russian-slides regression.
  const perLine = Math.max(1, widthInches * 5.5);
  // Also count forced \n breaks as extra lines.
  const hardBreaks = (text.match(/\n/g) || []).length;
  const wrapped = Math.ceil((text || "").length / perLine);
  return Math.max(1, wrapped + hardBreaks);
}

function resolveMarpRender() {
  // marp-slide is expected as a sibling skill: ../../marp-slide/scripts/render.py
  // from this file's directory (skills/pptx/scripts/md2pptx.js).
  const candidates = [
    path.resolve(__dirname, "..", "..", "marp-slide", "scripts", "render.py"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function preprocessMermaidForMarp(inputMd) {
  // marp's PPTX rasteriser does not honour ``<svg width="100%">`` reliably,
  // and our local mmdc gives SVG by default, so fenced ```mermaid blocks
  // disappear in the output. Pre-render them to PNG ourselves and rewrite
  // the source MD to reference the PNGs as plain images. Then run marp
  // with --no-mermaid so its own preprocessor doesn't undo our work.
  if (!hasMermaid()) return { mdPath: inputMd, didPreprocess: false, cleanup: () => {} };
  const src = fs.readFileSync(inputMd, "utf-8");
  if (!/```mermaid/.test(src)) {
    return { mdPath: inputMd, didPreprocess: false, cleanup: () => {} };
  }
  const inputDir = path.dirname(path.resolve(inputMd));
  const stem = path.basename(inputMd, path.extname(inputMd));
  const assetsDir = path.join(inputDir, `${stem}_assets`);
  fs.mkdirSync(assetsDir, { recursive: true });

  const re = /```mermaid\s*\n([\s\S]*?)\n```/g;
  let count = 0;
  const rewritten = src.replace(re, (full, body) => {
    const png = renderMermaid(body);
    if (!png) return full;
    const hash = crypto.createHash("sha1").update(body).digest("hex").slice(0, 12);
    const dst = path.join(assetsDir, `diagram-${hash}.png`);
    if (!fs.existsSync(dst)) fs.copyFileSync(png, dst);
    count++;
    const rel = path.relative(inputDir, dst).split(path.sep).join("/");
    return `![Diagram](${rel})`;
  });
  if (count === 0) {
    return { mdPath: inputMd, didPreprocess: false, cleanup: () => {} };
  }
  const tmpMd = path.join(inputDir, `.${stem}.md2pptx-${process.pid}.md`);
  fs.writeFileSync(tmpMd, rewritten, "utf-8");
  console.error(`[via-marp] pre-rendered ${count} mermaid block(s) to PNG`);
  return {
    mdPath: tmpMd,
    didPreprocess: true,
    cleanup: () => { try { fs.unlinkSync(tmpMd); } catch (e) {} },
  };
}

function renderViaMarp(inputMd, outputPptx, marpTheme) {
  const render = resolveMarpRender();
  if (!render) {
    console.error(
      "--via-marp: marp-slide skill not found at ../../marp-slide/scripts/render.py. " +
      "Install the marp-slide skill alongside pptx (see skills/marp-slide/) or drop the flag."
    );
    return 2;
  }
  const pp = preprocessMermaidForMarp(inputMd);
  try {
    // --pptx-editable is always passed: marp's default PPTX mode
    // rasterises each slide to a single PNG background, which drops
    // externally-referenced images (such as our pre-rendered mermaid
    // diagrams). Editable mode emits a proper PPTX with separate
    // text/image shapes. It requires LibreOffice (`soffice`) on PATH;
    // render.py fails with a helpful message if it's missing.
    const cmd = ["python3", JSON.stringify(render),
                 JSON.stringify(pp.mdPath),
                 "--format", "pptx",
                 "--output", JSON.stringify(outputPptx),
                 "--pptx-editable"];
    if (pp.didPreprocess) cmd.push("--no-mermaid");
    if (marpTheme) cmd.push("--theme", JSON.stringify(marpTheme));
    execSync(cmd.join(" "), { stdio: "inherit" });
    return 0;
  } catch (e) {
    const code = (e && typeof e.status === "number") ? e.status : 1;
    console.error(`--via-marp: render failed (exit ${code})`);
    return code;
  } finally {
    pp.cleanup();
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args) {
    console.error(
      "Usage: md2pptx.js INPUT.md OUTPUT.pptx [options]\n\n" +
      "Options:\n" +
      "  --size 16:9|4:3       Slide aspect ratio (default 16:9)\n" +
      "  --theme PATH          JSON theme overrides for the built-in renderer\n" +
      "  --via-marp            Delegate rendering to the marp-slide skill (higher quality\n" +
      "                        for prose-heavy MD). Mermaid blocks are pre-rendered to PNG\n" +
      "                        and the final PPTX uses --pptx-editable (requires LibreOffice).\n" +
      "                        Needs ../marp-slide/ with its scripts/install.sh run.\n" +
      "  --marp-theme NAME     When using --via-marp, override theme (default, minimal, tech, etc.)"
    );
    process.exit(1);
  }
  if (!fs.existsSync(args.input)) {
    console.error(`Input not found: ${args.input}`);
    process.exit(1);
  }

  if (args.viaMarp) {
    const code = renderViaMarp(args.input, args.output, args.marpTheme);
    process.exit(code);
  }

  const md = fs.readFileSync(args.input, "utf-8");
  const theme = loadTheme(args.themePath);
  const slidesMd = splitSlides(md);

  if (slidesMd.length === 0) {
    console.error("No slide content found in input.");
    process.exit(1);
  }

  const pres = new pptxgen();
  pres.layout = args.size === "4:3" ? "LAYOUT_4x3" : "LAYOUT_16x9";
  pres.theme = { headFontFace: theme.heading.fontFace, bodyFontFace: theme.body.fontFace };
  const pageLayout = {
    slideW: args.size === "4:3" ? 10.0 : 10.0,
    slideH: args.size === "4:3" ? 7.5 : 5.625,
  };

  let rendered = 0;
  let paginated = 0;
  let totalSkipped = 0;
  for (let i = 0; i < slidesMd.length; i++) {
    const result = renderSlide(pres, slidesMd[i], theme, i + 1, pageLayout);
    rendered += result.rendered;
    paginated += result.paginated;
    totalSkipped += result.skipped;
  }

  if (rendered === 0) {
    console.error("No renderable slides produced — refusing to write an empty deck.");
    process.exit(1);
  }

  await pres.writeFile({ fileName: args.output });
  const summary = `Wrote ${rendered} slide${rendered === 1 ? "" : "s"} to ${args.output}`;
  const parts = [];
  if (paginated > 0) parts.push(`${paginated} source slide(s) auto-paginated`);
  if (totalSkipped > 0) parts.push(`${totalSkipped} block(s) truncated`);
  console.log(parts.length > 0 ? `${summary} (${parts.join(", ")})` : summary);
}

main().catch(err => {
  console.error(`pptxgenjs failed: ${err.message}`);
  process.exit(1);
});
