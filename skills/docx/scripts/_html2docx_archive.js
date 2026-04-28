// _html2docx_archive.js — Bundle extractors for html2docx.js.
//
// Handles two single-file webpage archive formats:
//   * Safari `.webarchive` — Apple binary plist (`bplist00`) with
//     `WebMainResource` (HTML) + `WebSubresources` (images, CSS, etc.).
//   * Chrome / IE `.mhtml` / `.mht` — RFC 822 / 2557 multipart/related
//     MIME message; main `text/html` part + image/* sub-parts.
//
// Both produce `{ html: string, tmpDir: string }` and populate the shared
// `extractedImages` Map (URL → local path) consumed by the walker via
// `resolveLocalImagePath` to swap in the locally-extracted asset.

const fs = require('fs');
const os = require('os');
const path = require('path');
const bplist = require('bplist-parser');

const extractedImages = new Map();

// --- temp-dir lifecycle --------------------------------------------------
// Each archive extraction creates a temp directory that holds the embedded
// images for the duration of the run. Once `Packer.toBuffer` finishes the
// images are baked into the in-memory document tree, so the directory is
// no longer needed. Clean up on process exit (and on common signals) so
// we don't leak ~MB of plain-text Confluence assets into /var/folders/...
// after every invocation.
const _tmpDirs = [];
function _registerForCleanup(dir) { _tmpDirs.push(dir); }
function _cleanupTmpDirs() {
    while (_tmpDirs.length > 0) {
        const d = _tmpDirs.pop();
        try { fs.rmSync(d, { recursive: true, force: true }); } catch (_) { /* ignore */ }
    }
}
let _cleanupRegistered = false;
function _ensureCleanupRegistered() {
    if (_cleanupRegistered) return;
    _cleanupRegistered = true;
    process.on('exit', _cleanupTmpDirs);
    // SIGINT/SIGTERM defaults are non-zero exits that bypass 'exit'; wire
    // them explicitly so Ctrl-C also cleans up.
    for (const sig of ['SIGINT', 'SIGTERM']) {
        process.on(sig, () => { _cleanupTmpDirs(); process.exit(sig === 'SIGINT' ? 130 : 143); });
    }
}

function detectInputFormat(filePath) {
    if (/\.webarchive$/i.test(filePath)) return 'webarchive';
    if (/\.(mhtml|mht)$/i.test(filePath)) return 'mhtml';
    // Safari downloads sometimes drop the extension — magic-byte fallback.
    try {
        const fd = fs.openSync(filePath, 'r');
        const buf = Buffer.alloc(8);
        fs.readSync(fd, buf, 0, 8, 0);
        fs.closeSync(fd);
        if (buf.toString('ascii') === 'bplist00') return 'webarchive';
    } catch (_) { /* fall through */ }
    return 'html';
}

function extensionForMime(mime) {
    const m = (mime || '').toLowerCase();
    if (m === 'image/png') return '.png';
    if (m === 'image/jpeg' || m === 'image/jpg') return '.jpg';
    if (m === 'image/gif') return '.gif';
    if (m === 'image/svg+xml') return '.svg';
    if (m === 'image/bmp') return '.bmp';
    if (m === 'image/webp') return '.webp';
    return '';
}

// Filename safety: most filesystems cap a single component at 255 bytes.
// Long base64 data URLs (seen on real Confluence webarchives) ballooned
// past that. 80 chars is plenty for a basename.
function safeBaseName(rawBase, mime, fallbackIndex) {
    let base = path.basename((rawBase || '').split('?')[0] || '').replace(/[^A-Za-z0-9._-]/g, '_');
    if (!base) base = `image-${fallbackIndex}`;
    if (base.length > 80) {
        const ext = path.extname(base);
        base = base.slice(0, 80 - ext.length) + ext;
    }
    if (!path.extname(base)) base = base + (extensionForMime(mime) || '.bin');
    return base;
}

function uniqueWritePath(dir, name) {
    let outName = name, n = 1;
    while (fs.existsSync(path.join(dir, outName))) {
        outName = `${n}-${name}`;
        n++;
    }
    return path.join(dir, outName);
}

// Register an extracted image under both the absolute URL and the
// path-only form (`/download/foo.png?v=1`). Confluence-style HTML in a
// webarchive references images by path, while the bundle stores them by
// absolute URL — without both keys the lookup misses.
function addExtractedImage(url, fullPath) {
    if (!url || !fullPath) return;
    extractedImages.set(url, fullPath);
    try {
        const parsed = new URL(url);
        const pathPart = parsed.pathname + (parsed.search || '');
        if (pathPart && pathPart !== '/') extractedImages.set(pathPart, fullPath);
    } catch (_) { /* not a fully-qualified URL */ }
}

function extractWebArchive(archivePath, reportError) {
    let parsed;
    try {
        parsed = bplist.parseBuffer(fs.readFileSync(archivePath));
    } catch (err) {
        reportError(`Failed to parse .webarchive: ${err.message}`, 1, 'WebArchiveParseError');
    }
    const root = (parsed && parsed[0]) || {};
    const main = root.WebMainResource;
    if (!main || main.WebResourceData === undefined) {
        reportError('Invalid .webarchive: missing WebMainResource', 1, 'WebArchiveInvalid');
    }
    let html;
    if (Buffer.isBuffer(main.WebResourceData)) {
        const enc = String(main.WebResourceTextEncodingName || 'UTF-8').toLowerCase();
        const nodeEnc = (enc === 'utf-8' || enc === 'utf8') ? 'utf-8' : enc;
        try {
            html = main.WebResourceData.toString(nodeEnc);
        } catch (_) {
            console.warn(`html2docx: text-encoding "${enc}" not supported by Node Buffer.toString — falling back to utf-8 (text may be corrupted)`);
            html = main.WebResourceData.toString('utf-8');
        }
    } else {
        html = String(main.WebResourceData);
    }

    _ensureCleanupRegistered();
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'html2docx-webarchive-'));
    _registerForCleanup(tmpDir);
    const subs = [].concat(root.WebSubresources || []);
    let imgCount = 0;
    for (let i = 0; i < subs.length; i++) {
        const s = subs[i] || {};
        if (!s.WebResourceData || !Buffer.isBuffer(s.WebResourceData)) continue;
        const mime = String(s.WebResourceMIMEType || '').toLowerCase();
        if (!mime.startsWith('image/')) continue;
        const url = String(s.WebResourceURL || '');
        if (url.startsWith('data:')) continue;
        const base = safeBaseName(url, mime, i);
        const fullPath = uniqueWritePath(tmpDir, base);
        try {
            fs.writeFileSync(fullPath, s.WebResourceData);
        } catch (err) {
            console.warn(`html2docx: failed to write sub-resource (${base}): ${err.message}`);
            continue;
        }
        addExtractedImage(url, fullPath);
        imgCount++;
    }
    console.log(`html2docx: extracted ${imgCount} image sub-resource(s) from .webarchive to ${tmpDir}`);
    return { html, tmpDir };
}

// --- MHTML helpers -------------------------------------------------------

function parseMimeHeaders(blockStr) {
    // Returns { lower-cased-name: raw-value } with continuation lines folded.
    const out = {};
    const lines = blockStr.split(/\r?\n/);
    let cur = null;
    for (const line of lines) {
        if (/^\s/.test(line) && cur) {
            out[cur] += ' ' + line.trim();
            continue;
        }
        const m = line.match(/^([!-9;-~]+)\s*:\s*(.*)$/);
        if (!m) continue;
        cur = m[1].toLowerCase();
        out[cur] = m[2];
    }
    return out;
}

function getHeaderParam(headerValue, name) {
    if (!headerValue) return null;
    const re = new RegExp(`(?:^|;)\\s*${name}\\s*=\\s*("([^"]*)"|([^;\\s]+))`, 'i');
    const m = headerValue.match(re);
    if (!m) return null;
    return m[2] !== undefined ? m[2] : m[3];
}

function decodeQuotedPrintable(latinStr) {
    return latinStr
        .replace(/=\r?\n/g, '')
        .replace(/=([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
}

function decodePartBody(rawBuf, encoding) {
    const enc = (encoding || '').toLowerCase();
    if (enc === 'base64') {
        return Buffer.from(rawBuf.toString('ascii').replace(/\s+/g, ''), 'base64');
    }
    if (enc === 'quoted-printable') {
        return Buffer.from(decodeQuotedPrintable(rawBuf.toString('latin1')), 'latin1');
    }
    return rawBuf; // 7bit / 8bit / binary
}

function findBoundaryPositions(data, boundaryToken, fromIndex) {
    // Some MHTML emitters use bare LF instead of CRLF — try both.
    const positions = [];
    const variants = [
        Buffer.from('\r\n--' + boundaryToken),
        Buffer.from('\n--' + boundaryToken),
    ];
    // RFC 2046 allows an empty preamble — i.e. the first boundary may sit
    // at the very start of the body with no leading newline. Chrome
    // always inserts a CRLF; other emitters may not.
    const bareToken = Buffer.from('--' + boundaryToken);
    if (data.length >= fromIndex + bareToken.length &&
        data.slice(fromIndex, fromIndex + bareToken.length).equals(bareToken)) {
        positions.push({ at: fromIndex, len: bareToken.length });
    }
    let from = fromIndex;
    while (true) {
        let bestIdx = -1, bestLen = 0;
        for (const v of variants) {
            const idx = data.indexOf(v, from);
            if (idx !== -1 && (bestIdx === -1 || idx < bestIdx)) {
                bestIdx = idx;
                bestLen = v.length;
            }
        }
        if (bestIdx === -1) break;
        positions.push({ at: bestIdx, len: bestLen });
        from = bestIdx + bestLen;
    }
    return positions;
}

function extractMhtml(filePath, reportError) {
    const data = fs.readFileSync(filePath);
    let hdrEnd = data.indexOf(Buffer.from('\r\n\r\n'));
    let hdrSepLen = 4;
    if (hdrEnd === -1) {
        hdrEnd = data.indexOf(Buffer.from('\n\n'));
        hdrSepLen = 2;
    }
    if (hdrEnd === -1) reportError('Invalid MHTML: no header/body separator', 1, 'MhtmlInvalid');
    const topHeaders = parseMimeHeaders(data.slice(0, hdrEnd).toString('utf-8'));
    const boundary = getHeaderParam(topHeaders['content-type'] || '', 'boundary');
    if (!boundary) reportError('Invalid MHTML: no multipart boundary', 1, 'MhtmlInvalid');

    const positions = findBoundaryPositions(data, boundary, hdrEnd + hdrSepLen);
    if (positions.length < 2) reportError('Invalid MHTML: too few boundary markers', 1, 'MhtmlInvalid');

    const parts = [];
    for (let i = 0; i < positions.length - 1; i++) {
        const afterBoundary = positions[i].at + positions[i].len;
        const lineEnd = data.indexOf(0x0A, afterBoundary);
        if (lineEnd === -1) continue;
        const partStart = lineEnd + 1;
        const partEnd = positions[i + 1].at;
        if (partStart < partEnd) parts.push(data.slice(partStart, partEnd));
    }

    _ensureCleanupRegistered();
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'html2docx-mhtml-'));
    _registerForCleanup(tmpDir);
    let mainHtml = null;
    let imgCount = 0;
    for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        let sep = part.indexOf(Buffer.from('\r\n\r\n'));
        let sepLen = 4;
        if (sep === -1) {
            sep = part.indexOf(Buffer.from('\n\n'));
            sepLen = 2;
        }
        if (sep === -1) continue;
        const headers = parseMimeHeaders(part.slice(0, sep).toString('utf-8'));
        const bodyRaw = part.slice(sep + sepLen);
        const cte = (headers['content-transfer-encoding'] || '').toLowerCase();
        const partCt = (headers['content-type'] || '').toLowerCase();
        const loc = headers['content-location'] || '';
        let body = decodePartBody(bodyRaw, cte);
        // Strip the trailing CRLF that precedes the boundary.
        if (body.length >= 2 && body[body.length - 2] === 0x0D && body[body.length - 1] === 0x0A) {
            body = body.slice(0, body.length - 2);
        } else if (body.length >= 1 && body[body.length - 1] === 0x0A) {
            body = body.slice(0, body.length - 1);
        }
        if (mainHtml === null && partCt.startsWith('text/html')) {
            const charset = (getHeaderParam(partCt, 'charset') || 'utf-8').toLowerCase();
            const nodeEnc = (charset === 'utf-8' || charset === 'utf8') ? 'utf-8' : charset;
            try {
                mainHtml = body.toString(nodeEnc);
            } catch (_) {
                console.warn(`html2docx: charset "${charset}" not supported by Node Buffer.toString — falling back to utf-8 (text may be corrupted)`);
                mainHtml = body.toString('utf-8');
            }
        } else if (partCt.startsWith('image/')) {
            if (!loc || loc.startsWith('data:')) continue;
            const mimeOnly = partCt.split(';')[0].trim();
            const base = safeBaseName(loc, mimeOnly, i);
            const fullPath = uniqueWritePath(tmpDir, base);
            try {
                fs.writeFileSync(fullPath, body);
            } catch (err) {
                console.warn(`html2docx: failed to write MHTML part (${base}): ${err.message}`);
                continue;
            }
            addExtractedImage(loc, fullPath);
            imgCount++;
        }
    }
    if (mainHtml === null) reportError('MHTML had no text/html part', 1, 'MhtmlInvalid');
    console.log(`html2docx: extracted ${imgCount} image part(s) from MHTML to ${tmpDir}`);
    return { html: mainHtml, tmpDir };
}

module.exports = {
    extractedImages,
    detectInputFormat,
    extractWebArchive,
    extractMhtml,
    addExtractedImage,
};
