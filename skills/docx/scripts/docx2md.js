const fs = require("fs");
const path = require("path");

let globalNodeModulesCache = null;
let installLock = false;

// Dependency loader with fallback for local vs global installations
function loadDependency(name) {
    const { execSync } = require('child_process');
    try {
        // First try: local project installation or bundled
        return require(name);
    } catch (localErr) {
        try {
            // Second try: global npm installation (using absolute path execution context)
            if (!globalNodeModulesCache) {
                globalNodeModulesCache = execSync('npm root -g').toString().trim();
            }
            const globalPath = path.join(globalNodeModulesCache, name);
            return require(globalPath);
        } catch (globalErr) {
            if (installLock) {
                console.error(`[docx-to-md] Cannot auto-install ${name}: another installation is already in progress.`);
                process.exit(1);
            }

            console.log(`[docx-to-md] Dependency '${name}' not found. Auto-installing locally...`);
            try {
                installLock = true;
                // Third try: Auto-install locally in the directory where the script resides
                const scriptDir = path.dirname(__filename);
                execSync(`npm install ${name} --no-save`, { cwd: scriptDir, stdio: 'inherit' });
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

const mammoth = loadDependency("mammoth");
const TurndownService = loadDependency("turndown");
const turndownPluginGfm = loadDependency("turndown-plugin-gfm");
const inputDocx = process.argv[2];
const outputMd = process.argv[3];

if (!inputDocx || !outputMd) {
    console.error("Usage: node docx2md.js <input.docx> <output.md>");
    process.exit(1);
}

const outputDir = path.dirname(path.resolve(outputMd));
const baseName = path.basename(outputMd, ".md");
const imagesDirName = `${baseName}_images`;
const imagesDirPath = path.join(outputDir, imagesDirName);

let imageCounter = 1;

const options = {
    convertImage: mammoth.images.inline(function (element) {
        return element.read("base64").then(function (imageBuffer) {
            if (!fs.existsSync(imagesDirPath)) {
                fs.mkdirSync(imagesDirPath, { recursive: true });
            }
            const ext = element.contentType.split("/")[1] || "png";
            const imageName = `image_${String(imageCounter++).padStart(3, '0')}.${ext}`;
            const imagePath = path.join(imagesDirPath, imageName);
            fs.writeFileSync(imagePath, Buffer.from(imageBuffer, "base64"));

            // Return link relative to the markdown file (URL encoded for spaces)
            return {
                src: encodeURI(path.posix.join(imagesDirName, imageName))
            };
        });
    }),
    styleMap: [
        "p[style-name='Heading 1'] => h1:fresh",
        "p[style-name='Heading 2'] => h2:fresh",
        "p[style-name='Heading 3'] => h3:fresh",
        "p[style-name='Heading 4'] => h4:fresh",
        "p[style-name='Heading 5'] => h5:fresh",
        "p[style-name='Heading 6'] => h6:fresh",
        "p[style-name='Code'] => pre > code:fresh"
    ]
};

// Clean up images directory before extracting
if (fs.existsSync(imagesDirPath)) {
    fs.rmSync(imagesDirPath, { recursive: true, force: true });
}

console.log(`Converting:\n  Input:  ${inputDocx}\n  Output: ${outputMd}`);
mammoth.convertToHtml({ path: inputDocx }, options)
    .then(function (result) {
        let html = result.value;
        const messages = result.messages;

        if (messages.length > 0) {
            console.warn("Mammoth notices:");
            messages.forEach(m => console.warn(` - ${m.type}: ${m.message}`));
        }

        const turndownService = new TurndownService({
            headingStyle: 'atx',
            codeBlockStyle: 'fenced'
        });

        turndownService.use(turndownPluginGfm.gfm);

        // Custom rules to fix Mammoth HTML tables into Markdown tables
        turndownService.addRule('tableCell', {
            filter: ['th', 'td'],
            replacement: function (content) {
                // Return content with a trailing pipe.
                // Replace newlines inside cells with space to keep markdown table row intact.
                return ' ' + content.trim().replace(/\n+/g, ' ') + ' |';
            }
        });

        turndownService.addRule('tableRow', {
            filter: 'tr',
            replacement: function (content, node) {
                let border = '';
                // If it's the first row, add the markdown table header separator
                if (node.parentNode.nodeName === 'THEAD' || (node.parentNode.nodeName === 'TBODY' && node.previousSibling === null)) {
                    // Count how many cells are in this row to generate correct separator length
                    const cellCount = node.childNodes.filter(n => n.nodeName === 'TH' || n.nodeName === 'TD').length;
                    border = '\n|' + '---|'.repeat(cellCount);
                }
                return '\n|' + content + border;
            }
        });

        turndownService.addRule('table', {
            filter: function (node) {
                return node.nodeName === 'TABLE';
            },
            replacement: function (content) {
                // Clean up empty lines between rows
                content = content.replace(/\n\s*\n/g, '\n');
                return '\n\n' + content + '\n\n';
            }
        });

        turndownService.addRule('tableSection', {
            filter: ['thead', 'tbody', 'tfoot'],
            replacement: function (content) {
                return content;
            }
        });

        const markdown = turndownService.turndown(html);
        fs.writeFileSync(outputMd, markdown, "utf8");
        console.log(`\nSuccessfully converted and extracted ${imageCounter - 1} images.`);
    })
    .catch(function (err) {
        console.error("Error during conversion:", err);
        process.exit(1);
    });
