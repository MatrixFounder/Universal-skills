// Image asset pipeline: dedup + EMF→PNG batch + header/footer extraction +
// markdown href rewrite. All functions receive a shared `ctx` object:
//
//   ctx.imagesDirPath  — absolute dir where assets land on disk
//   ctx.imagesDirName  — basename used in markdown href
//   ctx.soffice        — path to soffice binary or null
//   ctx.seenHashes     — Map<sha1, filename> for dedup
//   ctx.emfFilenames   — Array<string> of stored filenames awaiting EMF→PNG
//   ctx.counter        — { next() } closure returning the next asset ordinal
//   ctx.installDir     — for loadDependency's auto-install fallback

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");

const { loadDependency } = require("./_util");

const EMF_EXT_RE = /^(x-emf|emf)$/i;

function normalizeExt(rawExt) {
    const ext = (rawExt || "png").replace(/^\./, "").toLowerCase();
    return ext.split("+")[0]; // "svg+xml" → "svg"
}

// Store buffer, dedup by SHA1. Returns the filename (basename only) to use in
// markdown. EMF conversion is deferred — see batchConvertEmfToPng().
function storeOrDedup(ctx, buffer, rawExt) {
    const hash = crypto.createHash("sha1").update(buffer).digest("hex");
    if (ctx.seenHashes.has(hash)) {
        return ctx.seenHashes.get(hash);
    }
    const baseNum = String(ctx.counter.next()).padStart(3, "0");
    const ext = normalizeExt(rawExt);
    const filename = `image_${baseNum}.${ext}`;
    fs.writeFileSync(path.join(ctx.imagesDirPath, filename), buffer);
    if (EMF_EXT_RE.test(ext)) {
        ctx.emfFilenames.push(filename);
    }
    ctx.seenHashes.set(hash, filename);
    return filename;
}

// Batch convert all queued EMFs in a single soffice invocation. Returns a
// Map<originalEmfBasename, pngBasename> for files that converted. Original
// .x-emf names are kept on disk as fallback and restored even on soffice
// failure.
function batchConvertEmfToPng(ctx) {
    const conversions = new Map();
    if (!ctx.soffice || ctx.emfFilenames.length === 0) return conversions;
    // soffice expects canonical `.emf`, not `.x-emf`. Rename in place.
    // The map lets us restore original names in `finally` no matter what.
    const renamed = new Map(); // currentAbsPath -> originalAbsPath
    try {
        for (const f of ctx.emfFilenames) {
            if (!/\.x-emf$/i.test(f)) continue;
            const orig = path.join(ctx.imagesDirPath, f);
            const renamedTo = orig.replace(/\.x-emf$/i, ".emf");
            fs.renameSync(orig, renamedTo);
            renamed.set(renamedTo, orig);
        }
        const inputs = ctx.emfFilenames.map((f) =>
            path.join(ctx.imagesDirPath, f.replace(/\.x-emf$/i, ".emf")),
        );
        const env = { ...process.env };
        if (process.platform !== "darwin") {
            env.SAL_USE_VCLPLUGIN = "svp";
        }
        try {
            execFileSync(
                ctx.soffice,
                ["--headless", "--convert-to", "png", "--outdir", ctx.imagesDirPath, ...inputs],
                { stdio: "ignore", timeout: 180000, env },
            );
        } catch (e) {
            console.warn(`[docx-to-md] soffice batch convert exited non-zero (${e.message}); falling back to .x-emf for unconverted files.`);
        }
    } finally {
        for (const [current, original] of renamed) {
            if (fs.existsSync(current)) {
                try { fs.renameSync(current, original); } catch (_) { /* best-effort */ }
            }
        }
    }
    for (const f of ctx.emfFilenames) {
        const pngName = f.replace(/\.(x-emf|emf)$/i, ".png");
        const pngAbs = path.join(ctx.imagesDirPath, pngName);
        if (fs.existsSync(pngAbs) && fs.statSync(pngAbs).size > 0) {
            conversions.set(f, pngName);
        }
    }
    return conversions;
}

// Rewrites `imagesDirName/<emf>` href occurrences in the markdown string to
// their `.png` equivalent for successfully converted files. Uses split/join
// (literal replacement) because asset filenames are generated tokens with no
// regex metacharacters.
function rewriteEmfHrefsToPng(ctx, md, conversions) {
    let out = md;
    for (const [emfName, pngName] of conversions) {
        const oldHref = encodeURI(path.posix.join(ctx.imagesDirName, emfName));
        const newHref = encodeURI(path.posix.join(ctx.imagesDirName, pngName));
        out = out.split(oldHref).join(newHref);
    }
    return out;
}

// Extract images from word/header*.xml.rels and word/footer*.xml.rels.
// Mammoth only processes document.xml, so logos and running-titles are
// silently dropped otherwise. Returns Array<{source, filename}>.
function extractHeaderFooterImages(ctx, docxPath) {
    const JSZip = loadDependency("jszip", ctx.installDir);
    const data = fs.readFileSync(docxPath);
    return JSZip.loadAsync(data).then(async (zip) => {
        const results = [];
        const relFiles = Object.keys(zip.files)
            .filter((n) => /^word\/_rels\/(header|footer)\d*\.xml\.rels$/.test(n))
            .sort();
        const seenMedia = new Set();
        for (const relPath of relFiles) {
            const relXml = await zip.file(relPath).async("string");
            const source = relPath.match(/(header|footer)\d*/)[0];
            const re = /Target="(media\/[^"]+)"/g;
            let m;
            while ((m = re.exec(relXml)) !== null) {
                const mediaRel = m[1];
                const mediaFullPath = `word/${mediaRel}`;
                if (seenMedia.has(mediaFullPath)) continue;
                seenMedia.add(mediaFullPath);
                const entry = zip.file(mediaFullPath);
                if (!entry) continue;
                const buf = await entry.async("nodebuffer");
                const ext = path.extname(mediaFullPath).replace(/^\./, "").toLowerCase() || "png";
                const filename = storeOrDedup(ctx, buf, ext);
                results.push({ source, filename });
            }
        }
        return results;
    });
}

module.exports = {
    storeOrDedup,
    batchConvertEmfToPng,
    rewriteEmfHrefsToPng,
    extractHeaderFooterImages,
};
