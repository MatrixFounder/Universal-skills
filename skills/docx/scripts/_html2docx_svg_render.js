// _html2docx_svg_render.js — SVG → PNG raster pipeline with graceful tiers.
//
// Tier 1: headless Chrome / Chromium / Edge / Brave via spawnSync. Real
//         browser layout, so foreignObject + CSS word-wrap + custom fonts
//         render exactly like Confluence shows them. No npm dependency
//         on top of what ships with Node — but the host has to have a
//         Chromium-family browser available somewhere.
// Tier 2: @resvg/resvg-js + the walker's ad-hoc foreignObject parser.
//         Cross-platform prebuilt binary, no system dependency, but
//         doesn't run CSS layout — drawio diagrams degrade.
//
// Detection order on first call:
//   1. $HTML2DOCX_BROWSER env var (explicit override; empty/invalid →
//      Tier 1 disabled outright, do NOT fall through to host probe)
//   2. Conventional install paths for the OS (incl. snap/flatpak/etc.
//      on Linux for /snap/bin/chromium and /var/lib/flatpak symlinks)
//   3. PATH lookup for `google-chrome` / `chromium` / etc.
//   4. `puppeteer.executablePath()` — useful when CI wants opt-in
//      bundled Chromium without changing the html2docx default deps.
// Result is cached for the rest of the process; after >=2 consecutive
// Chrome render failures the cache is auto-invalidated and we switch
// the rest of the document to resvg-js.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

let _Resvg = null;
try { _Resvg = require('@resvg/resvg-js').Resvg; } catch (_) { /* optional */ }
let _PNG = null;
try { _PNG = require('pngjs').PNG; } catch (_) { /* optional, only used for crop */ }

// `undefined` ≡ not detected yet, `null` ≡ no browser, string ≡ executable.
let _chromePath = undefined;
let _announced = false;
let _consecutiveChromeFailures = 0;
let _renderCounter = 0;

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);

function _existsExec(p) {
    if (!p) return false;
    try {
        const st = fs.statSync(p);
        // Resolve symlinks: a broken link statSync still succeeds via
        // followSymlink default but the underlying target may be gone —
        // statSync would fail then. Either we have a regular file we can
        // exec, or we treat the link target as authoritative.
        return st.isFile();
    } catch (_) {
        return false;
    }
}

function _candidatesForPlatform() {
    if (process.platform === 'darwin') {
        return [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
        ];
    }
    if (process.platform === 'win32') {
        const localAppData = process.env.LOCALAPPDATA || '';
        const programFiles = process.env['PROGRAMFILES'] || 'C:\\Program Files';
        const programFilesX86 = process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)';
        return [
            path.join(programFiles, 'Google\\Chrome\\Application\\chrome.exe'),
            path.join(programFilesX86, 'Google\\Chrome\\Application\\chrome.exe'),
            path.join(localAppData, 'Google\\Chrome\\Application\\chrome.exe'),
            path.join(programFiles, 'Microsoft\\Edge\\Application\\msedge.exe'),
            path.join(programFilesX86, 'Microsoft\\Edge\\Application\\msedge.exe'),
            path.join(programFiles, 'Chromium\\Application\\chrome.exe'),
        ];
    }
    // Linux / *BSD: snap and flatpak install browsers outside the default
    // PATH for non-interactive shells, so probe their conventional
    // locations directly. Distro packages still get found via PATH lookup.
    return [
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/microsoft-edge',
        '/usr/bin/brave-browser',
        '/snap/bin/chromium',
        '/snap/bin/chromium-browser',
        '/var/lib/flatpak/exports/bin/com.google.Chrome',
        '/var/lib/flatpak/exports/bin/org.chromium.Chromium',
    ];
}

function _whichOnPath(name) {
    try {
        const cmd = process.platform === 'win32' ? 'where' : 'which';
        const r = spawnSync(cmd, [name], { encoding: 'utf-8' });
        if (r.status !== 0) return null;
        const line = (r.stdout || '').split(/\r?\n/)[0].trim();
        return _existsExec(line) ? line : null;
    } catch (_) {
        return null;
    }
}

function findChromePath() {
    if (_chromePath !== undefined) return _chromePath;
    // 1. Explicit override is honoured strictly: an empty or invalid
    //    HTML2DOCX_BROWSER value disables Tier 1 outright (don't fall
    //    through to host-wide auto-detect — that would defeat the user's
    //    intent of forcing the resvg fallback for benchmarking / CI
    //    determinism).
    if (Object.prototype.hasOwnProperty.call(process.env, 'HTML2DOCX_BROWSER')) {
        const explicit = process.env.HTML2DOCX_BROWSER;
        if (_existsExec(explicit)) { _chromePath = explicit; return _chromePath; }
        _chromePath = null;
        return null;
    }
    // 2. Conventional install paths.
    for (const p of _candidatesForPlatform()) {
        if (_existsExec(p)) { _chromePath = p; return p; }
    }
    // 3. PATH lookup.
    const names = process.platform === 'win32'
        ? ['chrome.exe', 'msedge.exe']
        : ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome', 'microsoft-edge', 'brave-browser'];
    for (const name of names) {
        const found = _whichOnPath(name);
        if (found) { _chromePath = found; return found; }
    }
    // 4. puppeteer bundled binary as opt-in (no hard dep — only used if
    //    the user happens to have installed puppeteer in this project).
    try {
        const puppeteer = require('puppeteer');
        const ep = typeof puppeteer.executablePath === 'function'
            ? puppeteer.executablePath()
            : null;
        if (_existsExec(ep)) { _chromePath = ep; return ep; }
    } catch (_) { /* puppeteer not installed; expected on default install */ }
    _chromePath = null;
    return null;
}

// Decide whether to pass `--no-sandbox`. Chrome's sandbox is the primary
// barrier between any HTML/JS we hand it and the host. We MUST not strip
// it on developer/CI workstations — the user opens Confluence/CMS exports
// that may include scripts or external `xlink:href`. Disable the sandbox
// only when:
//   - HTML2DOCX_ALLOW_NO_SANDBOX=1 is set (explicit opt-in for trusted CI)
//   - process is running as root (Docker / Lambda case where Chrome
//     refuses to start with the sandbox enabled)
function _shouldDisableSandbox() {
    if (process.env.HTML2DOCX_ALLOW_NO_SANDBOX === '1') return true;
    try {
        if (typeof process.getuid === 'function' && process.getuid() === 0) return true;
    } catch (_) { /* getuid undefined on Win — sandbox stays on */ }
    return false;
}

function _isValidPng(buf) {
    return Buffer.isBuffer(buf) && buf.length > PNG_MAGIC.length &&
           buf.slice(0, PNG_MAGIC.length).equals(PNG_MAGIC);
}

// Crop near-white pixels off ALL FOUR sides of a PNG buffer so the
// resulting raster is the tight bounding box of the actual content.
// Drawio's macro container is a fixed-size *display window* that hides
// content overflowing past `height` — we render at a deliberately taller
// viewport to capture everything, then snap the image back to its true
// content extent with this routine.
//
// Returns the original buffer unchanged if pngjs isn't available, the
// image is already tight, or decoding fails. Padding (in pixels) keeps a
// breathing strip of whitespace on each side post-crop.
function _trimPngWhitespace(buf, padding) {
    if (!_PNG) return buf;
    let png;
    try { png = _PNG.sync.read(buf); }
    catch (_) { return buf; }
    const { width, height, data } = png;
    const threshold = 250;
    const rowIsWhite = (y) => {
        const start = y * width * 4;
        for (let x = 0; x < width; x++) {
            const i = start + x * 4;
            if (data[i] < threshold || data[i + 1] < threshold || data[i + 2] < threshold) return false;
        }
        return true;
    };
    const colIsWhite = (x, yStart, yEnd) => {
        for (let y = yStart; y < yEnd; y++) {
            const i = (y * width + x) * 4;
            if (data[i] < threshold || data[i + 1] < threshold || data[i + 2] < threshold) return false;
        }
        return true;
    };
    let top = 0;
    while (top < height && rowIsWhite(top)) top++;
    let bottom = height;
    while (bottom > top && rowIsWhite(bottom - 1)) bottom--;
    if (bottom <= top) return buf; // entirely white — nothing meaningful to trim to
    let left = 0;
    while (left < width && colIsWhite(left, top, bottom)) left++;
    let right = width;
    while (right > left && colIsWhite(right - 1, top, bottom)) right--;
    if (right <= left) return buf;
    const pad = padding || 0;
    const newTop = Math.max(0, top - pad);
    const newLeft = Math.max(0, left - pad);
    const newBottom = Math.min(height, bottom + pad);
    const newRight = Math.min(width, right + pad);
    const newW = newRight - newLeft;
    const newH = newBottom - newTop;
    if (newW === width && newH === height) return buf;
    const cropped = new _PNG({ width: newW, height: newH });
    for (let y = 0; y < newH; y++) {
        const srcRow = ((y + newTop) * width + newLeft) * 4;
        const dstRow = (y * newW) * 4;
        data.copy(cropped.data, dstRow, srcRow, srcRow + newW * 4);
    }
    return _PNG.sync.write(cropped);
}

// Heuristic: how full is the bottom strip of the rendered PNG? If it's
// mostly non-white we likely truncated content and should re-render at a
// taller viewport. Returns 0..1 fill ratio for the bottom 5% strip.
function _bottomFillRatio(buf) {
    if (!_PNG) return 0;
    let png;
    try { png = _PNG.sync.read(buf); }
    catch (_) { return 0; }
    const { width, height, data } = png;
    const stripStart = Math.max(0, Math.floor(height * 0.95));
    const total = (height - stripStart) * width;
    if (total <= 0) return 0;
    let nonWhite = 0;
    const threshold = 250;
    for (let y = stripStart; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const i = (y * width + x) * 4;
            if (data[i] < threshold || data[i + 1] < threshold || data[i + 2] < threshold) nonWhite++;
        }
    }
    return nonWhite / total;
}

function _injectSvgNamespaces(svgXml) {
    return svgXml.replace(/<svg\b([^>]*)>/i, (_m, attrs) => {
        let augmented = attrs;
        if (!/\sxmlns\s*=/.test(attrs)) augmented += ' xmlns="http://www.w3.org/2000/svg"';
        if (!/\sxmlns:xlink\s*=/.test(attrs)) augmented += ' xmlns:xlink="http://www.w3.org/1999/xlink"';
        return `<svg${augmented}>`;
    });
}

function _runChromeOnce(svgXml, W, H, safeH, chrome) {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'html2docx-chrome-'));
    const htmlPath = path.join(tmpDir, 'in.html');
    const pngPath = path.join(tmpDir, 'out.png');
    const html = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
        'html,body{margin:0;padding:0;background:#fff;}' +
        '#wrap{width:' + W + 'px;height:' + H + 'px;overflow:visible;}' +
        '#wrap > svg{display:block;width:100%;height:100%;overflow:visible;}' +
        '</style></head><body><div id="wrap">' + svgXml + '</div></body></html>';
    fs.writeFileSync(htmlPath, html);
    const fileUrl = (process.platform === 'win32' ? 'file:///' : 'file://') +
        htmlPath.replace(/\\/g, '/');
    const baseArgs = [
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--hide-scrollbars',
        '--virtual-time-budget=2000',
        '--default-background-color=ffffffff',
        '--force-device-scale-factor=2',
        `--window-size=${Math.round(W)},${Math.round(safeH)}`,
        `--screenshot=${pngPath}`,
        fileUrl,
    ];
    // Sandbox is enabled by default; we strip it only when running as root
    // or when the caller opts in via env. Untrusted SVG (Confluence drawio
    // can include external xlink images) under --no-sandbox would let any
    // browser-process exploit reach the host filesystem.
    if (_shouldDisableSandbox()) baseArgs.unshift('--no-sandbox');
    // `--headless=old` honours --window-size for screenshots; `=new`
    // ignores it on some Chromium builds and captures default 1280×720.
    // Try old first, fall back to bare `--headless` for very old builds
    // that don't recognise the value. Always unlink the stale PNG between
    // attempts so we don't read partial bytes from a previous failure.
    const tries = [['--headless=old', ...baseArgs], ['--headless', ...baseArgs]];
    let lastErr = null;
    try {
        for (const argv of tries) {
            try { fs.unlinkSync(pngPath); } catch (_) { /* not present yet */ }
            const r = spawnSync(chrome, argv, {
                timeout: 30000,
                stdio: ['ignore', 'ignore', 'pipe'],
            });
            if (r.error) { lastErr = r.error; continue; }
            if (r.status !== 0) {
                lastErr = new Error(`exit=${r.status} ${(r.stderr || '').toString().slice(0, 300)}`);
                continue;
            }
            if (!fs.existsSync(pngPath)) {
                lastErr = new Error('Chrome exited 0 but produced no screenshot');
                continue;
            }
            const buf = fs.readFileSync(pngPath);
            if (!_isValidPng(buf)) {
                lastErr = new Error('Chrome wrote a corrupt PNG (magic mismatch)');
                continue;
            }
            return buf;
        }
        throw lastErr || new Error('Chrome render failed (no specific error)');
    } finally {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) { /* best-effort */ }
    }
}

function _renderViaChrome(svgXml, w, h, chrome) {
    const W = Math.max(1, Math.round(w));
    const H = Math.max(1, Math.round(h));
    // Render at an inflated viewport to catch content drawio hides via
    // `overflow: hidden` on its display window. If the bottom 5% of the
    // PNG is heavily non-white afterwards, content was probably clipped
    // — bump the viewport once more before settling. Empirically, two
    // passes cover all real-world drawio macros we've seen; cap at a hard
    // limit so a pathological diagram doesn't push us into 30 s timeouts.
    const passes = [
        Math.max(H * 1.7, H + 200),
        Math.max(H * 2.6, H + 400),
        Math.max(H * 4.0, H + 800),
    ];
    let png = null;
    for (let i = 0; i < passes.length; i++) {
        png = _runChromeOnce(svgXml, W, H, passes[i], chrome);
        if (i === passes.length - 1) break;
        if (_bottomFillRatio(png) < 0.05) break; // bottom is mostly white → content fits
    }
    // Padding 24 px (= 12 logical at 2× DPR) breathing room around the
    // tight content bbox so adjacent text in Word doesn't crowd the image.
    return _trimPngWhitespace(png, 24);
}

function _renderViaResvg(svgXml, w) {
    if (!_Resvg) throw new Error('@resvg/resvg-js not installed');
    return new _Resvg(svgXml, {
        fitTo: { mode: 'width', value: Math.max(1, Math.round(w * 2)) },
        background: 'rgba(255,255,255,1)',
    }).render().asPng();
}

// `chromeReadySvg` returns the SVG ready for Chrome (just needs xlink
// namespace fix). `resvgReadySvg` returns the SVG with all the heavier
// preprocessing (foreignObject → <text>, CSS function resolution,
// named-entity decode). Splitting them means Chrome users never pay for
// the resvg-only preprocessing pipeline.
function render({ chromeReadySvg, resvgReadySvg, width, height }) {
    _renderCounter++;
    const chrome = findChromePath();
    if (chrome) {
        if (!_announced) {
            console.log(`html2docx: SVG renderer = headless Chrome (${chrome})`);
            _announced = true;
        }
        try {
            const svg = _injectSvgNamespaces(chromeReadySvg());
            const result = _renderViaChrome(svg, width, height, chrome);
            _consecutiveChromeFailures = 0;
            return result;
        } catch (err) {
            _consecutiveChromeFailures++;
            console.warn(`html2docx: Chrome render failed (${err.message}); falling back to resvg-js`);
            // After 2 consecutive Chrome failures, give up on Tier 1 for
            // the rest of this run. Avoids spamming the same warning per
            // SVG and matches what users would expect on a broken Chrome
            // install (better one announce-message than 50 warnings).
            if (_consecutiveChromeFailures >= 2) {
                console.warn('html2docx: ≥2 consecutive Chrome failures — switching to resvg-js for the rest of this run');
                _chromePath = null;
            }
            // Fall through to resvg.
        }
    } else if (!_announced) {
        console.log('html2docx: SVG renderer = resvg-js (no Chrome detected — drawio diagrams may degrade)');
        console.log('html2docx: install Chrome/Chromium or set HTML2DOCX_BROWSER=/path/to/chrome for 100% fidelity');
        _announced = true;
    }
    return _renderViaResvg(resvgReadySvg(), width);
}

module.exports = {
    render,
    findChromePath,        // exposed for tests / startup messages
    _injectSvgNamespaces,  // re-used by the walker's resvg branch
    // Test-only exports — use sparingly.
    _trimPngWhitespace,
    _isValidPng,
    _shouldDisableSandbox,
};
