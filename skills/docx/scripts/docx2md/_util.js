// Leaf-level utilities for docx2md. No dependencies on sibling modules,
// safe to import from anywhere without creating cycles.

const path = require("path");

let globalNodeModulesCache = null;
let installLock = false;

// Load `name` from (in order) local node_modules, global npm, or auto-install
// into `installDir`. `installDir` must point at the directory whose
// node_modules/ should receive the package (the scripts/ root for this skill,
// regardless of which sub-module called in).
function loadDependency(name, installDir) {
    const { execSync } = require("child_process");
    try {
        return require(name);
    } catch (localErr) {
        try {
            if (!globalNodeModulesCache) {
                globalNodeModulesCache = execSync("npm root -g").toString().trim();
            }
            return require(path.join(globalNodeModulesCache, name));
        } catch (globalErr) {
            if (installLock) {
                console.error(`[docx-to-md] Cannot auto-install ${name}: another installation is already in progress.`);
                process.exit(1);
            }
            console.log(`[docx-to-md] Dependency '${name}' not found. Auto-installing locally...`);
            try {
                installLock = true;
                execSync(`npm install ${name} --no-save`, { cwd: installDir, stdio: "inherit" });
                installLock = false;
                return require(name);
            } catch (installErr) {
                installLock = false;
                console.error(`[docx-to-md] Failed to auto-install dependency: ${name}.`);
                console.error(`Please install it manually: npm install -g ${name}`);
                process.exit(1);
            }
        }
    }
}

// Normalize markdown/plain-text for fuzzy substring matching. Strips
// markdown emphasis, image refs, link syntax, heading markers, and
// collapses whitespace. Used by shape injection AND markdown post-processing
// so it lives in the shared leaf module.
function normalizeForMatching(s) {
    return s
        .replace(/\*\*|__|\*|_|`/g, "")
        .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
        .replace(/^\s*#+\s*/, "")
        .replace(/\s+/g, " ")
        .trim();
}

module.exports = { loadDependency, normalizeForMatching };
