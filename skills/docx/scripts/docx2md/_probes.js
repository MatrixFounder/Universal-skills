// External-tool detection. Pure: just probes PATH + well-known install
// locations with a tiny `--version`/`-v` invocation. Returns path-or-null
// for soffice and a {pdftoppm, pdftotext} object (or null) for poppler.

const { execFileSync } = require("child_process");

function findSoffice() {
    const candidates = [
        "soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/homebrew/bin/soffice",
    ];
    for (const c of candidates) {
        try {
            execFileSync(c, ["--version"], { stdio: "ignore", timeout: 10000 });
            return c;
        } catch (_) { /* try next */ }
    }
    return null;
}

// Poppler (pdftoppm + pdftotext) enables the high-fidelity shape-group path:
// docx → PDF (via soffice) → bbox-layout text extraction → tight-crop pdftoppm
// render. Without poppler we fall back to the LO HTML export, which gives
// geometry only (no text labels inside shapes).
function findPoppler() {
    const tools = ["pdftoppm", "pdftotext"];
    const resolved = {};
    for (const tool of tools) {
        const candidates = [
            tool,
            `/opt/homebrew/bin/${tool}`,
            `/usr/local/bin/${tool}`,
            `/usr/bin/${tool}`,
        ];
        let found = null;
        for (const c of candidates) {
            try {
                execFileSync(c, ["-v"], { stdio: "ignore", timeout: 5000 });
                found = c;
                break;
            } catch (_) { /* try next */ }
        }
        if (!found) return null;
        resolved[tool] = found;
    }
    return resolved;
}

module.exports = { findSoffice, findPoppler };
