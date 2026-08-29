#!/usr/bin/env node
// obsidian2md.js — Obsidian note → CommonMark (TASK 030).
//
// A thin CLI over _obsidian_lib.js. No conversion logic lives here: md2docx.js --obsidian
// requires the same library in-process, and any rule written here instead of there would
// apply to one route and not the other.
//
// Exit codes follow the skill's convention (docx_replace.py is the reference):
//   0 success · 1 I/O · 2 invalid argument or usage · 6 SelfOverwriteRefused
//   8 AssetNotFound (only under --strict-assets; code 8 was previously unused)

'use strict';

const fs = require('fs');
const path = require('path');
const lib = require('./_obsidian_lib');

const USAGE = [
    'Usage: node obsidian2md.js <input.md> <output.md>',
    '         [--vault-root DIR] [--frontmatter table|render|strip]',
    '         [--lang ru|en|auto] [--links text|italic]',
    '         [--inline-tags strip|keep] [--transclude] [--strict-assets]',
    '         [--json-errors]',
].join('\n');

const VALUE_FLAGS = new Set([
    '--vault-root', '--frontmatter', '--lang', '--links', '--inline-tags',
]);
const CHOICES = {
    '--frontmatter': ['table', 'render', 'strip'],
    '--lang': ['ru', 'en', 'auto'],
    '--links': ['text', 'italic'],
    '--inline-tags': ['strip', 'keep'],
};

// Decided BEFORE the parse loop, not inside it. This loop reports usage errors as it goes,
// so a `--json-errors` sitting to the RIGHT of the offending flag had not been read yet and
// the error came back as plain text — the machine-readable contract depended on argument
// ORDER, which is exactly what md2docx.js's own flag-order test forbids. html2docx.js never
// hit this because its loop cannot fail: an unknown option there becomes a positional and
// every error is raised after the parse (C5-14).
let jsonErrors = process.argv.slice(2).includes('--json-errors');

// Same shape as html2docx.js:95 and scripts/_errors.py: one line, schema-versioned.
function reportError(msg, code, type, details) {
    if (jsonErrors) {
        const env = { v: 1, error: String(msg), code };
        if (type) env.type = type;
        if (details && Object.keys(details).length) env.details = details;
        process.stderr.write(JSON.stringify(env) + '\n');
    } else {
        process.stderr.write(String(msg) + '\n');
    }
    process.exit(code);
}

function parseArgs(argv) {
    const opts = {
        frontmatter: 'table',
        lang: 'auto',
        links: 'text',
        inlineTags: 'strip',
        transclude: false,
        strictAssets: false,
        vaultRoot: null,
    };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--json-errors') {
            jsonErrors = true;
        } else if (a === '--transclude') {
            opts.transclude = true;
        } else if (a === '--strict-assets') {
            opts.strictAssets = true;
        } else if (VALUE_FLAGS.has(a)) {
            if (i + 1 >= argv.length) {
                reportError(`Missing value for ${a}\n${USAGE}`, 2, 'UsageError', { flag: a });
            }
            const v = argv[++i];
            if (CHOICES[a] && !CHOICES[a].includes(v)) {
                reportError(
                    `Invalid value for ${a}: "${v}" (expected ${CHOICES[a].join('|')})`,
                    2, 'UsageError', { flag: a, value: v, expected: CHOICES[a] });
            }
            if (a === '--vault-root') opts.vaultRoot = v;
            else if (a === '--frontmatter') opts.frontmatter = v;
            else if (a === '--lang') opts.lang = v;
            else if (a === '--links') opts.links = v;
            else opts.inlineTags = v;
        } else if (a === '--help' || a === '-h') {
            process.stdout.write(USAGE + '\n');
            process.exit(0);
        } else if (a.startsWith('--')) {
            reportError(`Unknown option: ${a}\n${USAGE}`, 2, 'UsageError', { flag: a });
        } else {
            positional.push(a);
        }
    }
    return { opts, positional };
}

function main() {
    const { opts, positional } = parseArgs(process.argv.slice(2));
    const [inputFile, outputFile] = positional;
    if (!inputFile || !outputFile) {
        reportError(USAGE, 2, 'UsageError');
    }

    const inputAbs = path.resolve(inputFile);
    const outputAbs = path.resolve(outputFile);

    // Refuse before reading, so a mistyped command cannot destroy the note (R1d).
    // resolve() also collapses `./` and `..`, catching `note.md` vs `./note.md`.
    let sameFile = inputAbs === outputAbs;
    if (!sameFile) {
        try {
            sameFile = fs.realpathSync(inputAbs) === fs.realpathSync(outputAbs);
        } catch (e) { /* output may not exist yet — not the same file */ }
    }
    if (sameFile) {
        reportError(
            `Refusing to overwrite the input in place: ${inputFile}`,
            6, 'SelfOverwriteRefused', { path: inputAbs });
    }

    if (opts.vaultRoot !== null) {
        try {
            if (!fs.statSync(opts.vaultRoot).isDirectory()) throw new Error('not a directory');
        } catch (e) {
            reportError(`--vault-root is not a directory: ${opts.vaultRoot}`,
                2, 'UsageError', { path: opts.vaultRoot });
        }
    }

    let text;
    try {
        text = fs.readFileSync(inputAbs, 'utf-8');
    } catch (e) {
        reportError(`Cannot read input: ${e.message}`, 1, 'IOError', { path: inputAbs });
    }

    let result;
    try {
        result = lib.convert(text, {
            notePath: inputAbs,
            vaultRoot: opts.vaultRoot,
            frontmatter: opts.frontmatter,
            lang: opts.lang,
            links: opts.links,
            inlineTags: opts.inlineTags,
            transclude: opts.transclude,
        });
    } catch (e) {
        reportError(`Conversion failed: ${e.message}`, 1, 'ConversionError');
    }

    for (const w of result.warnings) process.stderr.write(`warning: ${w}\n`);

    if (opts.strictAssets && result.missing.length) {                   // R7(b)
        reportError(
            `${result.missing.length} attachment(s) not found: ${result.missing.join(', ')}`,
            8, 'AssetNotFound', { missing: result.missing });
    }

    try {
        fs.writeFileSync(outputAbs, result.markdown, 'utf-8');
    } catch (e) {
        reportError(`Cannot write output: ${e.message}`, 1, 'IOError', { path: outputAbs });
    }

    process.stdout.write(
        `Converted ${path.basename(inputAbs)} → ${outputFile} `
        + `(${result.markdown.length} chars, lang=${result.lang}`
        + `${result.missing.length ? `, ${result.missing.length} missing` : ''})\n`);
}

if (require.main === module) main();

module.exports = { parseArgs, USAGE };
