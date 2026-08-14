// _obsidian_lib.js — Obsidian-flavoured Markdown → CommonMark.
//
// TASK 030. The conversion core, shared by two consumers inside this skill:
//   * scripts/obsidian2md.js        — the standalone CLI (.md → .md)
//   * scripts/md2docx.js --obsidian — the one-command route, requires this in-process
//
// This module knows NOTHING about OOXML. Its whole contract is text in, text out, so it
// is testable without building or unzipping a .docx, and so pdf/pptx/marp-slide could
// adopt it later without inheriting a Word dependency (TASK 030 §5 records why it is not
// replicated to them today).
//
// Why a pre-processor and not a `marked` extension: an Obsidian note is not CommonMark,
// and `marked.lexer` reports the difference as `text` tokens rather than as an error.
// Measured on the reference note at TASK 030 §1 — exit 0, valid .docx, five participants
// and two images missing. Normalising the syntax before the lexer sees it fixes the loss
// for every downstream consumer at once; a tokenizer extension would fix it for md2docx.js
// alone.
//
// Order of operations in convert() is load-bearing and is stated at each step below.

'use strict';

const fs = require('fs');
const path = require('path');

// --- Localisation ------------------------------------------------------------------
//
// R13: no user-visible string is written at its use site. `--lang auto` reads the note's
// own `lang:` frontmatter key, which is what the reference vault sets.

const MESSAGES = {
    en: {
        fmHeader: ['Field', 'Value'],
        labels: {
            participants: 'Participants',
            author: 'Author',
            published: 'Published',
            source: 'Source',
            tags: 'Tags',
        },
        notFound: (name) => `[image not found: ${name}]`,
        seeNote: (name) => `See note “${name}”`,
        fileRef: (name) => `File: ${name}`,
        callouts: {
            note: 'Note', tip: 'Tip', info: 'Info', todo: 'To do',
            abstract: 'Abstract', summary: 'Summary', tldr: 'TL;DR',
            question: 'Question', faq: 'FAQ', help: 'Help',
            warning: 'Warning', caution: 'Caution', attention: 'Attention',
            failure: 'Failure', fail: 'Failure', missing: 'Missing',
            danger: 'Danger', error: 'Error', bug: 'Bug',
            example: 'Example', quote: 'Quote', cite: 'Quote',
            success: 'Success', check: 'Success', done: 'Done',
            important: 'Important', hint: 'Hint', warn: 'Warning',
        },
    },
    ru: {
        fmHeader: ['Поле', 'Значение'],
        labels: {
            participants: 'Участники',
            author: 'Автор',
            published: 'Дата',
            source: 'Источник',
            tags: 'Теги',
        },
        notFound: (name) => `[изображение не найдено: ${name}]`,
        seeNote: (name) => `См. заметку «${name}»`,
        fileRef: (name) => `Файл: ${name}`,
        callouts: {
            note: 'Заметка', tip: 'Совет', info: 'Информация', todo: 'Сделать',
            abstract: 'Кратко', summary: 'Итог', tldr: 'Кратко',
            question: 'Вопрос', faq: 'Вопросы', help: 'Справка',
            warning: 'Внимание', caution: 'Осторожно', attention: 'Внимание',
            failure: 'Сбой', fail: 'Сбой', missing: 'Отсутствует',
            danger: 'Опасно', error: 'Ошибка', bug: 'Дефект',
            example: 'Пример', quote: 'Цитата', cite: 'Цитата',
            success: 'Готово', check: 'Готово', done: 'Готово',
            important: 'Важно', hint: 'Подсказка', warn: 'Внимание',
        },
    },
};

// --- Frontmatter key policy (R2d) --------------------------------------------------
//
// A module-level constant, not a literal inside renderFrontmatter(), so the displayed set
// is editable without reading the rendering code. `keys` are the accepted spellings in the
// note; `id` selects the label from MESSAGES.labels.

const FRONTMATTER_KEYS = [
    { id: 'participants', keys: ['participants', 'attendees'] },
    { id: 'author', keys: ['author', 'authors'] },
    { id: 'published', keys: ['published', 'date'] },
    { id: 'source', keys: ['url', 'source'] },
    { id: 'tags', keys: ['tags'] },
];

// R2(f). Machine keys for the vault's own index, plus `tldr` which duplicates the body.
// Compared case-folded, because Obsidian templates ship both `Created` and `created`.
const FRONTMATTER_SUPPRESS = new Set([
    'type', 'slug', 'vault_id', 'created', 'updated', 'sources', 'tldr', 'lang',
    'title', 'aliases', 'cssclasses', 'publish', 'permalink',
]);

// Kept in lockstep with `detectImageType()` in md2docx.js — an extension listed here but
// missing there resolves to a real path and then throws `Unsupported image format` at build
// time. `webp` is deliberately ABSENT for that reason: the docx image layer accepts
// png/jpg/gif/bmp/svg only, so `![[x.webp]]` becomes a named file reference (R3d) instead of
// a crash. TASK 030 R3(f) records the departure.
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg']);

// Directories never worth walking when indexing a vault (R5h). `.trash` is Obsidian's own
// soft-delete folder: indexing it resurrects deleted attachments.
const SKIP_DIRS = new Set(['.obsidian', '.git', 'node_modules', '.trash', '.DS_Store']);

const MAX_TRANSCLUDE_DEPTH = 3;

// --- Code masking (R10) -------------------------------------------------------------
//
// Every rewrite below is a regex over the whole document, so each one would happily edit
// the inside of a fenced block. A note that DOCUMENTS Obsidian syntax — this repository is
// full of them — would have its examples silently rewritten. Mask first, restore last.
//
// The sentinel is NUL-delimited. That is not on its own a guarantee: U+0000 IS valid UTF-8
// and `readFileSync(path, 'utf-8')` preserves it, so a note carrying the sentinel's own bytes
// could make `unmaskCode` splice an unrelated stored code region into that position, or leave
// a literal `obsmask` in the document. `stripControlChars()` removes NUL from the source
// before any masking runs, which closes that and is required anyway: XML 1.0 forbids U+0000,
// so a NUL reaching the writer produces a .docx no reader will open.

const MASK_OPEN = '\u0000obsmask';
const MASK_CLOSE = '\u0000';

const LIST_ITEM = /^([ \t]*)([-*+]|\d+[.)])([ \t]+)/;
const BQ_PREFIX = /^((?:[ \t]*>[ \t]?)*)/;

/**
 * Mask every code region in `text`, appending to the caller's `store`.
 *
 * ONE line-based state machine, deliberately. The first four designs were regexes over the
 * whole document, and each shipped a defect that regex shape made unavoidable:
 *
 *   v1  a bare indented-code regex masked every tab-indented nested bullet, so embeds and
 *       wikilinks inside bullets reached the document literally at exit 0.        (CRITICAL)
 *   v2  a line walker fixed that; a fence INSIDE a list came back as a sentinel at column 0,
 *       was read as a flush line, and the next continuation was masked as code.       (HIGH)
 *   v3  stepping over the sentinel fixed that, and leaked list state PAST the list, so a
 *       genuine top-level indented code block was rewritten (`#include` deleted).     (HIGH)
 *   v4  recovering the block's indentation from the store fixed that, and still mis-read a
 *       fence indented 1-3 spaces, a fence inside a blockquote, and — worst — an unmatched
 *       backtick in prose, which paired with the NEXT code span and masked everything
 *       between, whole paragraphs at a time.                                      (CRITICAL)
 *
 * Every one of those is a question about line context — is this line inside a fence, inside a
 * list, inside a paragraph — which a regex over the whole document cannot answer. So the
 * state is explicit here and the regexes only ever match within one line or one paragraph.
 *
 * `store` and `keep` come from the CALLER so that a transcluded note masks into the SAME
 * store as its parent. Separate stores made a nested transclusion (A embeds B embeds C)
 * substitute the wrong text: C's code block was destroyed and B's duplicated in its place.
 */
function maskAll(text, keep) {
    const lines = text.split('\n');
    const out = [];
    let fence = null;             // {char, len, indent, bq, buf}
    let listIndent = -1;          // content indent of the open list item, -1 = no list
    let para = [];                // indices in `out` forming the current paragraph

    const flushParagraph = () => {
        if (!para.length) { para = []; return; }
        // Inline spans are masked WITHIN one paragraph. A code span cannot cross a blank
        // line, so bounding here is what stops one stray backtick from swallowing the rest
        // of the document by pairing with the next real span's opener.
        //
        // The write-back is a SPLICE, not index arithmetic over the old slots. Masking can
        // change a paragraph's line count (a multi-line span collapses to one sentinel), and
        // the arithmetic that tried to map the new lines back onto the old slots computed a
        // NEGATIVE slice offset — which JavaScript reads as "all but the last N", not as
        // "empty" — so lines were written into two slots each and the paragraph came out
        // DUPLICATED. An image inside such a paragraph was embedded twice.
        const start = para[0];
        const masked = maskInlineSpans(para.map((i) => out[i]).join('\n'), keep);
        out.splice(start, para.length, ...masked.split('\n'));
        para = [];
    };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const bq = BQ_PREFIX.exec(line)[1];
        // A CRLF note keeps its `\r` at the end of every line. The CLOSING-fence regex is
        // anchored with `$` and allows only spaces and tabs before it, so `` ```\r `` could
        // never close — while the OPENING regex's info-string class happily ate the `\r`.
        // Every fence therefore opened and none closed, and the unterminated-fence flush
        // masked the whole rest of the document: embeds, wikilinks and callouts after the
        // first fence reached the .docx literally, at exit 0, with --strict-assets silent.
        // Match on the stripped line; emit the original.
        const rest = line.slice(bq.length).replace(/\r$/, '');

        if (fence) {
            // A fence opened inside a blockquote ends where the blockquote does: the first
            // line that drops the `>` prefix leaves the quote, and an unterminated fence
            // must not then swallow the rest of the document. Without this, one blockquoted
            // snippet — routine when quoting chat or a PR review — masked every embed and
            // wikilink after it, at exit 0.
            if (fence.bq && !bq) {
                out.push(keep(fence.buf.join('\n')));
                fence = null;
                i--;                                   // re-read this line outside the fence
                continue;
            }
            fence.buf.push(line);
            const close = /^([ \t]{0,3})(`{3,}|~{3,})[ \t]*$/.exec(rest);
            if (close && close[2][0] === fence.char && close[2].length >= fence.len) {
                out.push(keep(fence.buf.join('\n')));
                fence = null;
            }
            continue;
        }

        // A fence opener: 0-3 spaces of indent (4+ is indented code), any info string.
        // CommonMark forbids a backtick in a BACKTICK fence's info string, and allows one
        // in a tilde fence's. Applying the backtick rule to both meant `~~~`js` was not
        // recognised as a fence at all, and its contents were rewritten.
        const open = /^([ \t]{0,3})(?:(`{3,})([^`]*)|(~{3,})(.*))$/.exec(rest);
        if (open) {
            flushParagraph();
            // Indent is measured on the fence itself, not on a sentinel that swallowed it —
            // that is what v3 got wrong. A fence starting left of the open list item's
            // content closes the list.
            const marker = open[2] || open[4];
            const indent = open[1].replace(/\t/g, '    ').length;
            if (listIndent >= 0 && indent < listIndent) listIndent = -1;
            fence = { char: marker[0], len: marker.length, bq, buf: [line] };
            continue;
        }

        if (!rest.trim()) { flushParagraph(); out.push(line); continue; }

        const item = LIST_ITEM.exec(rest);
        if (item) {
            flushParagraph();
            // CommonMark: a list item's CONTENT starts after the marker and its spaces.
            // Using marker-indent + 1 made a fence indented 1-3 spaces look like list
            // content, so the list never closed and the following indented code block was
            // left visible to every rewrite (`#include <stdio.h>` came back as `<stdio.h>`).
            listIndent = item[1].replace(/\t/g, '    ').length
                + item[2].length + item[3].replace(/\t/g, '    ').length;
            out.push(line);
            para.push(out.length - 1);
            continue;
        }

        const indentStr = /^[ \t]*/.exec(rest)[0];
        const indent = indentStr.replace(/\t/g, '    ').length;

        // Indented code: 4+ columns, outside any list, and only after a blank line —
        // CommonMark forbids it from interrupting a paragraph.
        if (indent >= 4 && listIndent < 0 && !para.length) {
            const buf = [];
            while (i < lines.length) {
                const l = lines[i];
                const r = l.slice(BQ_PREFIX.exec(l)[1].length);
                if (!r.trim()) {
                    // A blank line continues the block only if more indented code follows.
                    // EVERY blank in the run is kept: pushing one and jumping the cursor past
                    // the rest deleted them from the document, so the masked region restored
                    // different bytes than it captured — the code block's own content edited.
                    let j = i + 1;
                    while (j < lines.length && !lines[j].slice(BQ_PREFIX.exec(lines[j])[1].length).trim()) j++;
                    const nxt = j < lines.length ? lines[j].slice(BQ_PREFIX.exec(lines[j])[1].length) : '';
                    if (!/^(?:[ ]{4}|\t)/.test(nxt)) break;
                    for (let k = i; k < j; k++) buf.push(lines[k]);
                    i = j;
                    continue;
                }
                if (!/^(?:[ ]{4}|\t)/.test(r)) break;
                buf.push(l); i++;
            }
            i--;
            if (buf.length) out.push(keep(buf.join('\n')));
            continue;
        }

        if (indent < listIndent && listIndent >= 0) listIndent = -1;
        out.push(line);
        para.push(out.length - 1);
    }

    if (fence) out.push(keep(fence.buf.join('\n')));   // unterminated: to EOF
    flushParagraph();
    return out.join('\n');
}

/**
 * Mask balanced inline code spans inside ONE paragraph.
 *
 * CommonMark's rule: an opening run of N backticks closes on the next run of EXACTLY N.
 * A run with no partner is literal text and must be left alone — the v4 regex instead let it
 * pair with the opener of the next genuine span, masking every paragraph in between.
 */
/** Is the character at `i` preceded by an odd number of backslashes, i.e. escaped? */
function isEscaped(text, i) {
    let n = 0;
    while (i - n - 1 >= 0 && text[i - n - 1] === '\\') n++;
    return n % 2 === 1;
}

function maskInlineSpans(text, keep) {
    let out = '';
    let i = 0;
    while (i < text.length) {
        if (text[i] !== '`') { out += text[i++]; continue; }
        // A backslash-escaped backtick is literal text, not a delimiter. Treating it as an
        // opener let it pair with the next real span and mask everything between — the same
        // shape as the cycle-4 stray-backtick CRITICAL, through a different door.
        if (isEscaped(text, i)) { out += text[i++]; continue; }
        let n = 0;
        while (text[i + n] === '`') n++;
        const openRun = text.slice(i, i + n);
        let j = i + n;
        let found = -1;
        while (j < text.length) {
            if (text[j] === '`' && !isEscaped(text, j)) {
                let m = 0;
                while (text[j + m] === '`') m++;
                if (m === n) { found = j; break; }
                j += m;
            } else j++;
        }
        if (found === -1) { out += openRun; i += n; continue; }   // unmatched: literal
        out += keep(text.slice(i, found + n));
        i = found + n;
    }
    return out;
}

function unmaskCode(text, store) {
    // Repeat until stable: a masked inline span can sit inside a masked fenced block.
    let out = text;
    for (let pass = 0; pass < 8; pass++) {
        const next = out.replace(
            new RegExp(MASK_OPEN + '(\\d+)' + MASK_CLOSE, 'g'),
            (m, i) => (store[Number(i)] !== undefined ? store[Number(i)] : m));
        if (next === out) break;
        out = next;
    }
    return out;
}

/**
 * Remove characters that cannot appear in a `.docx` — and that would otherwise let a note
 * forge a mask sentinel.
 *
 * XML 1.0 permits only tab, newline, carriage return and U+0020 upward among the C0 range, so
 * these bytes could never survive into the output anyway. Dropping them here rather than at
 * the writer keeps the masking invariant simple: nothing in the text can look like a sentinel.
 */
function stripControlChars(text) {
    return text.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');
}

/** A store plus the `keep` that appends to it. One per convert() run, shared with children. */
function newMaskStore() {
    const store = [];
    const keep = (raw) => {
        store.push(raw);
        return MASK_OPEN + (store.length - 1) + MASK_CLOSE;
    };
    return { store, keep };
}

// --- Frontmatter --------------------------------------------------------------------

/**
 * Split a leading YAML frontmatter block off `text`.
 *
 * Anchored at offset 0 (R10d) so a `---` thematic break in the body is never eaten. This
 * is the same anchoring md2docx.js:57 uses; the difference is that this function KEEPS
 * what it removes.
 *
 * The parser covers the YAML subset Obsidian actually writes — `key: value`, block lists,
 * flow lists, quoted scalars — rather than pulling in a YAML dependency, because R17(d)
 * requires this task to add none.
 */
function parseFrontmatter(text) {
    const m = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
    if (!m) return { data: {}, body: text, raw: null };

    const data = {};
    let key = null;
    for (const rawLine of m[1].split(/\r?\n/)) {
        const line = rawLine.replace(/\s+$/, '');
        if (!line.trim() || /^\s*#/.test(line)) continue;

        const top = /^([A-Za-z_][\w .-]*)\s*:\s*(.*)$/.exec(line);
        if (top && !/^\s/.test(line)) {
            key = top[1].trim();
            const value = top[2].trim();
            if (!value) {
                data[key] = [];
            } else if (/^\[.*\]$/.test(value)) {
                data[key] = value.slice(1, -1).split(',')
                    .map((s) => unquote(s.trim())).filter(Boolean);
            } else if (value === '|' || value === '>' || value === '|-' || value === '>-') {
                data[key] = [];            // block scalar; lines collected below
            } else {
                data[key] = unquote(value);
            }
            continue;
        }

        const item = /^\s*-\s+(.*)$/.exec(line);
        if (item && key !== null) {
            if (!Array.isArray(data[key])) data[key] = data[key] ? [data[key]] : [];
            data[key].push(unquote(item[1].trim()));
            continue;
        }

        // A continuation line of a block scalar, or a nested mapping we do not model.
        if (key !== null && /^\s+\S/.test(line) && Array.isArray(data[key])) {
            data[key].push(line.trim());
        }
    }
    return { data, body: text.slice(m[0].length), raw: m[1] };
}

function unquote(s) {
    const t = String(s).trim();
    if (t.length >= 2 && ((t[0] === '"' && t.endsWith('"')) || (t[0] === "'" && t.endsWith("'")))) {
        return t.slice(1, -1);
    }
    return t;
}

/** Cell-safe text: a pipe would end the column, a newline would end the row (R2h). */
function cellSafe(value) {
    return String(value)
        .replace(/\r?\n+/g, ' ')
        .replace(/\|/g, '\\|')
        .trim();
}

function frontmatterRows(data, msg) {
    const seen = new Set();
    const rows = [];
    for (const spec of FRONTMATTER_KEYS) {
        for (const candidate of spec.keys) {
            const actual = Object.keys(data).find(
                (k) => k.toLowerCase() === candidate && !seen.has(k));
            if (actual === undefined) continue;
            const value = data[actual];
            const list = Array.isArray(value) ? value.filter((v) => String(v).trim()) : [value];
            if (!list.length || !String(list[0]).trim()) continue;
            seen.add(actual);
            rows.push({ id: spec.id, label: msg.labels[spec.id], values: list.map(String) });
            break;
        }
    }
    return rows;
}

/**
 * Re-emit the reader-relevant frontmatter keys as Markdown.
 *
 * `table` is the DEFAULT (R2). It emits a GFM table rather than building anything
 * Word-specific, so md2docx.js's existing `table` token path renders it — same 1pt CCCCCC
 * borders, same D5E8F0 header shading, same column arithmetic as every other table in the
 * document (md2docx.js:60 and :320). That is the whole reason this is a table of Markdown
 * and not a docx Table object: styling stays in one place.
 *
 * Multi-valued keys use `<br>` inside the cell. A GFM cell cannot hold a block list, and
 * `<br>` is handled by md2docx.js's inline text path (verified: one `<w:br/>`, each value
 * its own run), which reads better than joining five attendees with commas.
 */
function renderFrontmatter(data, mode, msg) {
    if (mode === 'strip') return '';
    const rows = frontmatterRows(data, msg);
    if (!rows.length) return '';                                     // R2(i)

    if (mode === 'render') {
        const out = [];
        for (const row of rows) {
            if (row.values.length > 1) {
                out.push(`**${row.label}:**`, '');
                out.push(...row.values.map((v) => `- ${v}`));
                out.push('');
            } else {
                out.push(`**${row.label}:** ${row.values[0]}`, '');
            }
        }
        return out.join('\n').replace(/\n+$/, '\n');
    }

    // mode === 'table'
    const lines = [
        `| ${cellSafe(msg.fmHeader[0])} | ${cellSafe(msg.fmHeader[1])} |`,
        '|---|---|',
    ];
    for (const row of rows) {
        lines.push(`| ${cellSafe(row.label)} | ${row.values.map(cellSafe).join('<br>')} |`);
    }
    return lines.join('\n') + '\n';
}

/** Insert `block` after the H1, or at the top when the note has none (R2j). */
function insertAfterH1(body, block) {
    if (!block) return body;
    const lines = body.split('\n');
    const h1 = lines.findIndex((l) => /^#\s+\S/.test(l));
    if (h1 === -1) {
        return block + '\n' + body.replace(/^\n+/, '');
    }
    // Step over the source blockquote lines Obsidian templates put under the H1, so the
    // table lands after the note's provenance block rather than splitting it.
    let at = h1 + 1;
    while (at < lines.length && (!lines[at].trim() || lines[at].startsWith('>'))) at++;
    const head = lines.slice(0, at);
    const tail = lines.slice(at);
    while (head.length && !head[head.length - 1].trim()) head.pop();
    return head.concat(['', block.replace(/\n+$/, ''), ''], tail).join('\n');
}

// --- Destinations (R6) ---------------------------------------------------------------

/**
 * Render `p` as a Markdown image destination that `marked` lexes as an `image` token AND
 * that survives md2docx.js's `decodeURI()`.
 *
 * Two forms, and the choice between them is not cosmetic:
 *   * angle-bracket `<...>` — carries spaces verbatim, which every vault path has;
 *   * percent-encoded — used when the path holds a character the angle-bracket form
 *     cannot carry (`<`, `>`, newline) or a literal `%`.
 *
 * The `%` case is the subtle one. resolveLocalImagePath() calls `decodeURI(href)`
 * unguarded (md2docx.js:123), and `decodeURI("100% coverage.png")` raises
 * `URIError: URI malformed` — an uncaught throw on a perfectly legal filename. encodeURI()
 * turns `%` into `%25` first, so the round-trip is exact. Parentheses are escaped by hand
 * afterwards: encodeURI leaves them alone and an unescaped `)` would end the destination.
 */
function safeDestination(p) {
    if (/[<>\n\r%]/.test(p)) {
        return encodeURI(p).replace(/\(/g, '%28').replace(/\)/g, '%29');
    }
    return '<' + p + '>';
}

// --- Asset resolution (R5) ------------------------------------------------------------

function foldName(s) {
    // macOS hands out NFD; a note written on iOS carries NFC. Comparing the two forms
    // byte-wise finds nothing for any Cyrillic filename.
    return s.normalize('NFC').toLowerCase();
}

/** Walk up from `startDir` to the nearest ancestor holding `.obsidian/` (R5f). */
function findVaultRoot(startDir) {
    let dir = path.resolve(startDir);
    for (;;) {
        if (isDirectory(path.join(dir, '.obsidian'))) return dir;
        const up = path.dirname(dir);
        if (up === dir) return path.resolve(startDir);
        dir = up;
    }
}

function isDirectory(p) {
    try { return fs.statSync(p).isDirectory(); } catch (e) { return false; }
}

/**
 * Is `child` inside `root` once BOTH sides are resolved through their symlinks?
 *
 * The first version compared `path.resolve()` output as strings, which a directory symlink
 * inside the vault walks straight through: the string stays under the vault while the bytes
 * come from anywhere on disk. Comparison happens on realpath'd values, and a path that
 * cannot be realpath'd (it does not exist yet) is rejected rather than assumed safe.
 */
function isInside(root, child) {
    let realRoot;
    let realChild;
    try { realRoot = fs.realpathSync(root); } catch (e) { return false; }
    try { realChild = fs.realpathSync(child); } catch (e) { return false; }
    return realChild === realRoot || realChild.startsWith(realRoot + path.sep);
}

function isFile(p) {
    try { return fs.statSync(p).isFile(); } catch (e) { return false; }
}

/**
 * Read `attachmentFolderPath` from the vault's own config.
 *
 * The value is untrusted input: `app.json` travels with a vault, and a vault can arrive
 * from someone else. A value of `../../../etc` would aim attachment resolution outside the
 * vault, and whatever it resolved to would be embedded into the output .docx. So an
 * ABSOLUTE or escaping value is refused here rather than confined later — the note's own
 * links can still name an absolute path (R5c, declared non-confined), but the vault's
 * config file does not get to redirect every lookup.
 */
function readAttachmentFolder(vaultRoot, warnings) {
    let value;
    try {
        const raw = fs.readFileSync(path.join(vaultRoot, '.obsidian', 'app.json'), 'utf-8');
        value = JSON.parse(raw).attachmentFolderPath;
    } catch (e) {
        return null;
    }
    if (typeof value !== 'string' || !value.trim()) return null;
    const folder = value.trim();
    if (path.isAbsolute(folder)) {
        if (warnings) warnings.push(`ignoring absolute attachmentFolderPath in app.json: ${folder}`);
        return null;
    }
    // `./x` is note-relative and cannot be checked against the vault root here (the note
    // may sit anywhere under it); everything else is vault-relative and must stay inside.
    if (!folder.startsWith('./')) {
        const resolved = path.resolve(vaultRoot, folder);
        const inside = resolved === vaultRoot
            || resolved.startsWith(vaultRoot + path.sep);
        if (!inside) {
            if (warnings) warnings.push(`ignoring attachmentFolderPath that escapes the vault: ${folder}`);
            return null;
        }
    } else if (folder.split('/').includes('..')) {
        if (warnings) warnings.push(`ignoring attachmentFolderPath containing "..": ${folder}`);
        return null;
    }
    return folder;
}

/**
 * Index every file under the vault by folded basename, once per run (R5g).
 *
 * `lstatSync` rather than `statSync` on directories: following a symlink here can walk a
 * cycle, or leave the vault entirely into a synced folder the user never named.
 */
function buildVaultIndex(vaultRoot) {
    const index = new Map();
    const stack = [vaultRoot];
    let budget = 200000;
    while (stack.length && budget > 0) {
        const dir = stack.pop();
        let entries;
        try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { continue; }
        for (const entry of entries) {
            budget--;
            if (SKIP_DIRS.has(entry.name)) continue;
            const full = path.join(dir, entry.name);
            if (entry.isSymbolicLink()) continue;
            if (entry.isDirectory()) {
                stack.push(full);
            } else if (entry.isFile()) {
                const key = foldName(entry.name);
                if (!index.has(key)) index.set(key, []);
                index.get(key).push(full);
            }
        }
    }
    return index;
}

/**
 * Resolve an Obsidian attachment reference in Obsidian's own precedence order (R5a-e).
 * Returns an absolute path, or null.
 */
function resolveAsset(target, ctx) {
    const candidates = [];

    // (a) the vault's configured attachment folder.
    if (ctx.attachmentFolder) {
        const folder = ctx.attachmentFolder;
        if (folder.startsWith('./')) {
            candidates.push(path.resolve(ctx.noteDir, folder.slice(2), target));
        } else if (folder === '.') {
            candidates.push(path.resolve(ctx.noteDir, target));
        } else if (path.isAbsolute(folder)) {
            candidates.push(path.resolve(folder, target));
        } else {
            candidates.push(path.resolve(ctx.vaultRoot, folder, target));
        }
    }
    // (b) the note's own directory, and (c) the literal path in the link.
    candidates.push(path.resolve(ctx.noteDir, target));
    if (path.isAbsolute(target)) candidates.push(target);
    candidates.push(path.resolve(ctx.vaultRoot, target));

    for (const candidate of candidates) {
        if (!isFile(candidate)) continue;
        // Candidate (a) comes from app.json, which travels with the vault. Confining it
        // only at parse time is a string check that a directory symlink inside the vault
        // defeats; confining it here compares realpath'd bytes.
        if (candidate === candidates[0] && ctx.attachmentFolder
            && !isInside(ctx.vaultRoot, candidate)) {
            ctx.warnings.push(
                `ignoring attachment reached through attachmentFolderPath that leaves the `
                + `vault: ${target}`);
            continue;
        }
        return candidate;
    }

    // (d) vault-wide search by basename.
    if (!ctx.index) ctx.index = buildVaultIndex(ctx.vaultRoot);
    const hits = ctx.index.get(foldName(path.basename(target)));
    if (hits && hits.length) {
        if (hits.length > 1) {                                        // R5(e)
            ctx.warnings.push(
                `ambiguous attachment "${target}" — ${hits.length} candidates, using the first: `
                + hits.join(', '));
        }
        return hits[0];
    }
    return null;
}

// --- Embeds and links (R3, R4) ---------------------------------------------------------

function extensionOf(name) {
    const ext = path.extname(name).replace(/^\./, '').toLowerCase();
    return ext;
}

/** Split `pic.png|300` / `note#Heading` into its parts. */
function splitTarget(inner) {
    const bar = inner.indexOf('|');
    const target = (bar === -1 ? inner : inner.slice(0, bar)).trim();
    const hint = bar === -1 ? '' : inner.slice(bar + 1).trim();
    const hash = target.indexOf('#');
    return {
        file: (hash === -1 ? target : target.slice(0, hash)).trim(),
        anchor: hash === -1 ? '' : target.slice(hash + 1).trim(),
        hint,
    };
}

/** `300` → w=300, `100x50` → w=100 h=50, anything else → no hint (R3b, R3c). */
function sizeHint(hint) {
    const m = /^(\d+)(?:x(\d+))?$/.exec(hint);
    if (!m) return null;
    return m[2] ? `w=${m[1]}x${m[2]}` : `w=${m[1]}`;
}

function rewriteEmbeds(text, ctx) {
    return text.replace(/!\[\[([^\]\n]+)\]\]/g, (whole, inner) => {
        const { file, hint } = splitTarget(inner);
        if (!file) return whole;
        const ext = extensionOf(file);

        if (IMAGE_EXTENSIONS.has(ext)) {
            const resolved = resolveAsset(file, ctx);
            if (!resolved) {
                ctx.missing.push(file);
                ctx.warnings.push(`attachment not found: ${file}`);
                return `*${ctx.msg.notFound(path.basename(file))}*`;   // R7(a)
            }
            const size = sizeHint(hint);
            const alt = (size ? size + '|' : '') + path.basename(file, path.extname(file));
            return `![${alt}](${safeDestination(resolved)})`;
        }

        if (!ext || ext === 'md') {                                    // a note (R3e)
            if (ctx.transclude) {
                const inlined = transclude(file, ctx);
                if (inlined !== null) return inlined;
            }
            return `*${ctx.msg.seeNote(path.basename(file, path.extname(file)))}*`;
        }

        // pdf / audio / video / anything else: name it, never embed it (R3d).
        return `*${ctx.msg.fileRef(path.basename(file))}*`;
    });
}

function rewriteLinks(text, ctx) {
    return text.replace(/\[\[([^\]\n]+)\]\]/g, (whole, inner) => {
        const bar = inner.indexOf('|');
        let label;
        if (bar !== -1) {
            // Split on the FIRST pipe only; the label keeps any further pipes (R4e).
            label = inner.slice(bar + 1).trim();
        } else {
            const target = inner.trim();
            const hash = target.indexOf('#');
            const file = hash === -1 ? target : target.slice(0, hash);
            const anchor = hash === -1 ? '' : target.slice(hash + 1);
            const base = file.split('/').pop().trim() || file.trim();
            if (anchor && !anchor.startsWith('^')) {
                label = `${base} → ${anchor.trim()}`;                  // R4(c)
            } else {
                label = base;                                          // R4(b), R4(d)
            }
        }
        if (!label) return whole;
        return ctx.links === 'italic' ? `*${label}*` : label;
    });
}

// --- Transclusion (R12) -----------------------------------------------------------------

function transclude(file, ctx) {
    const target = file.toLowerCase().endsWith('.md') ? file : file + '.md';
    const resolved = resolveAsset(target, ctx);
    if (!resolved) {
        ctx.missing.push(target);
        ctx.warnings.push(`transclusion target not found: ${file}`);
        return null;
    }
    const key = path.resolve(resolved);
    // Transclusion inlines the target's TEXT into the output document, so an unconfined
    // target is an arbitrary-file read: a note received from someone else could name
    // `../../../.ssh/id_rsa` (or ship a .md symlink to it) and have the contents typed into
    // the .docx. Attachments are embedded as opaque bytes and R5(i) declares them
    // unconfined; text inlining is a different risk and is confined here.
    if (!isInside(ctx.vaultRoot, key)) {
        ctx.warnings.push(
            `refusing to transclude a target outside the vault: ${file}`);
        return null;
    }
    if (ctx.visited.has(key)) {                                        // R12(e)
        ctx.warnings.push(`transclusion cycle at "${file}" — emitting a reference instead`);
        return null;
    }
    if (ctx.depth >= MAX_TRANSCLUDE_DEPTH) {                           // R12(c)
        ctx.warnings.push(`transclusion depth limit (${MAX_TRANSCLUDE_DEPTH}) at "${file}"`);
        return null;
    }

    let raw;
    try { raw = fs.readFileSync(key, 'utf-8'); } catch (e) {
        ctx.warnings.push(`cannot read transclusion target "${file}": ${e.message}`);
        return null;
    }

    ctx.visited.add(key);
    ctx.depth++;
    const inner = { ...ctx, noteDir: path.dirname(key) };
    const body = parseFrontmatter(stripControlChars(raw)).body;        // R12(b)
    // Masked into the PARENT's store, and NOT unmasked here. convert() unmasks once, at the
    // very end, over the whole document. Giving the child its own store made a nested
    // transclusion (A embeds B embeds C) substitute the wrong text — C masked into one store
    // and was unmasked against another, so C's code block was destroyed and B's duplicated
    // in its place.
    let out = maskAll(body, ctx.keep);
    out = stripComments(out);
    out = rewriteEmbeds(out, inner);
    out = rewriteLinks(out, inner);
    out = rewriteMinor(out, inner);
    out = rewriteCallouts(out, inner);
    out = absolutiseRelativeImages(out, inner.noteDir);
    // Demote WHILE MASKED, or this reads a `# comment` inside a shell fence as a heading and
    // edits the code it is inlining.
    out = out.replace(/^(#{1,5})\s/gm, '$1# ');                        // R12(a) demote
    // Removed on unwind: `visited` marks the notes on the CURRENT path, which is what
    // detects a cycle. Leaving entries behind made a DIAMOND (A embeds B and C, both of which
    // embed the same note) look like a cycle on its second, non-recursive occurrence — the
    // shared note was replaced by a pointer line and the run reported a cycle that did not
    // exist.
    ctx.visited.delete(key);
    ctx.depth--;
    return '\n' + out.trim() + '\n';
}

/**
 * Re-root plain CommonMark image destinations onto `dir`.
 *
 * Only needed for TRANSCLUDED text. md2docx.js resolves relative hrefs against the top-level
 * note's directory, which is right for that note and wrong for every note pulled into it —
 * a transcluded note's `![alt](img/pic.png)` silently pointed at the wrong folder. Wikilink
 * embeds never need this: rewriteEmbeds() already emits absolute paths.
 *
 * Remote, data:, absolute and angle-bracket destinations are left alone.
 */
function absolutiseRelativeImages(text, dir) {
    // Three destination shapes, not one: bare, angle-bracketed `<a b.png>`, and either of
    // those followed by a title. The first version matched only the bare form, so a
    // transcluded note whose image path contained a space — the shape this skill itself
    // emits — kept pointing at the parent's directory.
    return text.replace(
        /!\[([^\]]*)\]\(\s*(?:<([^>\n]*)>|([^)\s]+))((?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?)\s*\)/g,
        (whole, alt, angled, bare, title) => {
            const href = angled !== undefined ? angled : bare;
            if (!href) return whole;
            if (/^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(href)) return whole;
            let decoded;
            try { decoded = decodeURI(href); } catch (e) { decoded = href; }
            const abs = path.resolve(dir, decoded);
            if (!isFile(abs)) return whole;
            return `![${alt}](${safeDestination(abs)}${title || ''})`;
        });
}

// --- Callouts (R8) -------------------------------------------------------------------

function calloutLabel(type, msg) {
    const key = type.toLowerCase();
    if (msg.callouts[key]) return msg.callouts[key];
    return key.charAt(0).toUpperCase() + key.slice(1);                 // R8(c)
}

function rewriteCallouts(text, ctx) {
    return text.replace(
        /^([ \t]*)>\s*\[!([A-Za-z][\w-]*)\][-+]?[ \t]*(.*)$/gm,
        (whole, indent, type, title) => {
            const label = title.trim() || calloutLabel(type, ctx.msg);
            // A bold paragraph, then a blank quote line so the rest of the callout stays a
            // blockquote of its own. The `[!type]` marker never reaches the document.
            return `${indent}> **${label}**\n${indent}>`;
        });
}

// --- Minor syntax (R9) -----------------------------------------------------------------

function stripComments(text) {
    // A comment that sits INSIDE a line takes one of its flanking spaces with it, so
    // `word %%c%% word` does not become `word  word`. A comment that occupies whole lines
    // leaves them empty, which Markdown ignores.
    return text
        .replace(/[ \t]%%[\s\S]*?%%[ \t]/g, ' ')
        .replace(/%%[\s\S]*?%%/g, '');
}

function rewriteMinor(text, ctx) {
    let out = text;
    out = out.replace(/==([^=\n]+)==/g, '**$1**');                     // R9(a)
    out = out.replace(/^([ \t]*(?:[-*+]|\d+[.)])\s+)\[ \]\s+/gm, '$1☐ ');   // R9(d)
    out = out.replace(/^([ \t]*(?:[-*+]|\d+[.)])\s+)\[[xX]\]\s+/gm, '$1☑ ');
    if (ctx.inlineTags === 'strip') {                                  // R9(c)
        // A tag must start a word and carry at least one non-digit, so `#1` (an issue
        // reference) and a URL fragment are both left alone. `# Heading` cannot match:
        // the character after `#` is a space.
        // The lead class was `[\s(]`, which also matched the `(` of a Markdown link
        // destination — so `[text](#some-heading)` lost its anchor and became `[text]()`.
        // An Obsidian tag directly after `(` is not worth that: the lead is whitespace or
        // start-of-line only.
        // The numeric exclusion was a lookahead requiring whitespace-or-end after the
        // digits, so `#42.` `#7,` `#99!` all fell through it and were DELETED from ordinary
        // prose. Decide on the captured body instead: a tag that is only digits is an issue
        // reference, whatever punctuation follows it.
        const TAG = /(^|\s)#([\p{L}\p{N}_][\p{L}\p{N}_/-]*)/gmu;
        // Line by line, so the whitespace left behind by a removed tag is tidied ONLY on
        // lines that actually lost one. A document-wide trailing-space strip was the first
        // version and it deleted Markdown HARD LINE BREAKS (two trailing spaces) from every
        // line in the document — an edit nobody asked for, on notes with no tags at all.
        out = out.split('\n').map((line) => {
            TAG.lastIndex = 0;
            if (!TAG.test(line)) return line;
            TAG.lastIndex = 0;
            const stripped = line.replace(TAG,
                (m, lead, body) => (/^\d+$/.test(body) ? m : lead));
            if (stripped === line) return line;
            // The line's own INDENTATION is structure, not tag residue. Trimming it flush
            // turned `\t- nested item #tag` into `- nested item`, flattening a nested list
            // into a sibling and losing the outline in the .docx. Tidy inside the indent.
            const indent = /^[ \t]*/.exec(line)[0];
            const rest = stripped.startsWith(indent) ? stripped.slice(indent.length) : stripped;
            // Only the gap the tag itself left is tidied. Collapsing every `[ \t]{2,}` run
            // in the line reformatted content the author aligned on purpose — a tagged line
            // of `val  = 1   #tag` came back as `val = 1`.
            return indent + rest.replace(/^[ \t]+/, '').replace(/[ \t]+$/, '');
        }).join('\n');
    }
    return out;
}

// --- Entry point -----------------------------------------------------------------------

/**
 * Convert Obsidian-flavoured Markdown to CommonMark.
 *
 * @param {string} text  the note's source
 * @param {object} opts
 *   notePath      absolute path of the note (used for relative attachment resolution)
 *   vaultRoot     vault root; discovered by walking up to `.obsidian/` when omitted
 *   frontmatter   'table' (default) | 'render' | 'strip'
 *   lang          'auto' (default) | 'ru' | 'en'
 *   links         'text' (default) | 'italic'
 *   inlineTags    'strip' (default) | 'keep'
 *   transclude    false (default)
 * @returns {{markdown: string, warnings: string[], missing: string[], lang: string}}
 */
function convert(text, opts) {
    const options = opts || {};
    const notePath = options.notePath ? path.resolve(options.notePath) : process.cwd();
    const noteDir = isDirectory(notePath) ? notePath : path.dirname(notePath);
    const vaultRoot = options.vaultRoot
        ? path.resolve(options.vaultRoot)
        : findVaultRoot(noteDir);

    const parsed = parseFrontmatter(stripControlChars(text));
    const { data } = parsed;
    // Removing the frontmatter leaves the blank line that separated it from the H1. Trim
    // leading blanks ONLY when there was frontmatter to remove: a plain CommonMark file
    // that genuinely starts with blank lines must survive byte-identical (R14b).
    const body = parsed.raw === null ? parsed.body : parsed.body.replace(/^[ \t]*\r?\n+/, '');

    let lang = options.lang || 'auto';
    if (lang === 'auto') {
        const declared = Object.keys(data).find((k) => k.toLowerCase() === 'lang');
        const value = declared ? String(data[declared]).toLowerCase().slice(0, 2) : '';
        lang = MESSAGES[value] ? value : 'en';                          // R13(a)
    }
    const msg = MESSAGES[lang] || MESSAGES.en;

    const warnings = [];
    const ctx = {
        noteDir,
        vaultRoot,
        attachmentFolder: readAttachmentFolder(vaultRoot, warnings),
        index: null,
        msg,
        links: options.links || 'text',
        inlineTags: options.inlineTags || 'strip',
        transclude: Boolean(options.transclude),
        visited: new Set([notePath]),
        depth: 0,
        warnings,
        missing: [],
    };

    // Masking is FIRST and unmasking is LAST; every rewrite between them is blind to the
    // inside of a code block by construction rather than by each regex remembering to be.
    // ONE store for the whole run, shared with every transcluded note (see transclude()).
    const { store, keep } = newMaskStore();
    ctx.keep = keep;
    let out = maskAll(body, keep);
    out = stripComments(out);
    out = rewriteEmbeds(out, ctx);
    out = rewriteLinks(out, ctx);
    // rewriteMinor runs BEFORE rewriteCallouts. A callout title carrying an inline tag
    // (`> [!note] Title #tag`) was wrapped in bold first and stripped second, so the
    // trailing space landed INSIDE the emphasis and Word rendered a literal `**Title **`.
    // Stripping first lets the callout's own `title.trim()` finish the job.
    out = rewriteMinor(out, ctx);
    out = rewriteCallouts(out, ctx);
    // The table is placed while the code regions are STILL MASKED. insertAfterH1 finds the
    // first `# ` line, and a restored fenced block can contain one (a shell comment, a
    // diff header) — placing it after unmasking spliced the table into the middle of a
    // fence on any note with frontmatter and no H1, which is the normal Obsidian shape
    // where the title is the filename.
    const block = renderFrontmatter(data, options.frontmatter || 'table', msg);
    out = insertAfterH1(out, block);
    out = unmaskCode(out, store);

    // One trailing LF, idempotently (R14).
    out = out.replace(/\n*$/, '\n');

    return { markdown: out, warnings: ctx.warnings, missing: ctx.missing, lang };
}

module.exports = {
    convert,
    parseFrontmatter,
    renderFrontmatter,
    insertAfterH1,
    maskAll,
    maskInlineSpans,
    newMaskStore,
    unmaskCode,
    isInside,
    resolveAsset,
    rewriteEmbeds,
    rewriteLinks,
    absolutiseRelativeImages,
    rewriteCallouts,
    rewriteMinor,
    stripComments,
    safeDestination,
    splitTarget,
    sizeHint,
    findVaultRoot,
    buildVaultIndex,
    cellSafe,
    foldName,
    MESSAGES,
    FRONTMATTER_KEYS,
    FRONTMATTER_SUPPRESS,
    IMAGE_EXTENSIONS,
    SKIP_DIRS,
    MAX_TRANSCLUDE_DEPTH,
};
