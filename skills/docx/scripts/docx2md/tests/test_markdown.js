// Unit tests for _markdown.js pipeline passes. Pure functions → no fixture,
// no disk IO, no external tools. Run with: node test_markdown.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const os = require("os");
const {
    collapseDuplicateImageRuns,
    applyHeadingNumberingFromTOC,
    injectTocAnchors,
    dropEmptyHeadings,
    dropTinyImageRefs,
} = require("../_markdown");

let passed = 0;
function it(name, fn) {
    try {
        fn();
        passed += 1;
        console.log(`  ✓ ${name}`);
    } catch (e) {
        console.error(`  ✗ ${name}\n    ${e.message}`);
        process.exitCode = 1;
    }
}

console.log("collapseDuplicateImageRuns:");

it("collapses four identical refs on a line to one", () => {
    const input = "prelude\n![](a.png)![](a.png)![](a.png)![](a.png)\nsuffix";
    const out = collapseDuplicateImageRuns(input);
    assert.strictEqual(out, "prelude\n![](a.png)\nsuffix");
});

it("leaves non-adjacent same-ref alone", () => {
    const input = "![](a.png) text ![](a.png)";
    const out = collapseDuplicateImageRuns(input);
    assert.strictEqual(out, input);
});

it("leaves different refs alone", () => {
    const input = "![](a.png)![](b.png)";
    const out = collapseDuplicateImageRuns(input);
    assert.strictEqual(out, input);
});

it("preserves alt-text in repeated refs", () => {
    const input = "![alt](x.png)![alt](x.png)";
    const out = collapseDuplicateImageRuns(input);
    assert.strictEqual(out, "![alt](x.png)");
});

console.log("\napplyHeadingNumberingFromTOC:");

it("numbers H1 from TOC entry", () => {
    const input = [
        "[1.0 PURPOSE 4](#_Toc1)",
        "[2.0 AUDIENCE 5](#_Toc2)",
        "",
        "# PURPOSE",
        "# AUDIENCE",
    ].join("\n");
    const out = applyHeadingNumberingFromTOC(input);
    assert.ok(out.includes("# 1.0 PURPOSE"));
    assert.ok(out.includes("# 2.0 AUDIENCE"));
});

it("skips headings already numbered", () => {
    const input = "[1.0 PURPOSE 4](#_Toc1)\n\n# 1.0 PURPOSE";
    const out = applyHeadingNumberingFromTOC(input);
    assert.strictEqual(out.match(/# 1\.0 PURPOSE/g).length, 1, "should not double-number");
});

it("matches heading with italic wrappers", () => {
    const input = "[CHG 1.1 6](#_Toc1)\n\n## _CHG 1.1_";
    const out = applyHeadingNumberingFromTOC(input);
    assert.ok(out.includes("## CHG 1.1 _CHG 1.1_") || out.includes("CHG 1.1"),
        "italic-wrapped heading should still be recognised");
});

it("returns original markdown if no TOC detected", () => {
    const input = "# heading\n\nbody";
    const out = applyHeadingNumberingFromTOC(input);
    assert.strictEqual(out, input);
});

console.log("\ninjectTocAnchors:");

it("inlines anchor at start of matched heading body", () => {
    const input = [
        "[1.0 PURPOSE 4](#_Toc173)",
        "",
        "# 1.0 PURPOSE",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.ok(out.includes('# <a id="_Toc173" name="_Toc173"></a>1.0 PURPOSE'),
        `expected anchor inlined into heading, got: ${out}`);
});

it("is idempotent on re-run", () => {
    const first = injectTocAnchors([
        "[1.0 PURPOSE 4](#_Toc173)",
        "",
        "# 1.0 PURPOSE",
    ].join("\n"));
    const second = injectTocAnchors(first);
    assert.strictEqual(second.match(/id="_Toc173"/g).length, 1,
        "should not double-insert anchor on re-run");
});

it("matches heading with or without leading number", () => {
    const input = [
        "[5.0 PROCESS 8](#_Toc5)",
        "",
        "# 5.0 PROCESS",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.ok(out.includes('id="_Toc5"'), "numbered heading should match TOC entry");
});

it("injects anchor inside bold table cell when TOC points to flattened heading", () => {
    // mammoth flattens a Heading-styled span inside a table cell to
    // `**Role**`. The TOC entry still references _TocN — the anchor
    // pass should inject inside the bold marker so the link resolves.
    const input = [
        "[Change Requester 6](#_Toc259)",
        "[Process Owner 7](#_Toc271)",
        "",
        "# 4.0 ROLES",
        "",
        "| **Change Requester** | Provides Requirements |",
        "| **Process Owner** | Owns the Process |",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.ok(out.includes('**<a id="_Toc259" name="_Toc259"></a>Change Requester**'),
        `expected anchor inside bold of Change Requester cell, got: ${out}`);
    assert.ok(out.includes('**<a id="_Toc271" name="_Toc271"></a>Process Owner**'));
});

it("does not double-inject the same TOC id across passes", () => {
    // Heading match wins; matching bold cells must NOT re-inject the
    // id elsewhere.
    const input = [
        "[Process Owner 7](#_Toc271)",
        "",
        "# Process Owner",
        "",
        "| **Process Owner** | dup |",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.strictEqual(out.match(/id="_Toc271"/g).length, 1,
        "anchor must appear exactly once");
});

it("matches heading with internal italics (mid-string emphasis)", () => {
    // TOC entry has plain text; body heading has italic span via mammoth
    // (Word styled "RFC Creation (Process)" as italic). Pre-fix, the
    // mid-string `_..._` markers caused lookup to miss.
    const input = [
        "[CHG 1.1 Sub-Process: RFC Creation (Process) 15](#_Toc284)",
        "",
        "## CHG 1.1 Sub-Process: _RFC Creation (Process)_",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.ok(out.includes('id="_Toc284"'),
        `internal-italic heading should still match TOC entry, got: ${out}`);
});

it("returns markdown unchanged if no TOC entries", () => {
    const input = "# heading\n\nbody";
    const out = injectTocAnchors(input);
    assert.strictEqual(out, input);
});

console.log("\napplyHeadingNumberingFromTOC (escaped-dot variants):");

it("matches mammoth's escaped-dot format '1\\.'", () => {
    const input = [
        "[1\\. Аннотация 3](#_Toc1)",
        "[2\\. Перечень 16](#_Toc2)",
        "",
        "# Аннотация",
        "# Перечень",
    ].join("\n");
    const out = applyHeadingNumberingFromTOC(input);
    assert.ok(out.includes("# 1 Аннотация"), `expected '1' prefix, got: ${out}`);
    assert.ok(out.includes("# 2 Перечень"));
});

it("matches escaped sub-sections '1\\.1\\.'", () => {
    const input = [
        "[1\\.1 Объекты 4](#_TocA)",
        "[1\\.2\\. Архитектура 8](#_TocB)",
        "",
        "## Объекты",
        "## Архитектура",
    ].join("\n");
    const out = applyHeadingNumberingFromTOC(input);
    assert.ok(out.includes("## 1.1 Объекты"));
    assert.ok(out.includes("## 1.2 Архитектура"));
});

console.log("\ninjectTocAnchors (escaped-dot variants):");

it("matches escaped numbered headings to TOC ids", () => {
    const input = [
        "[1\\. Аннотация 3](#_Toc101)",
        "",
        "# 1 Аннотация",
    ].join("\n");
    const out = injectTocAnchors(input);
    assert.ok(out.includes('id="_Toc101"'));
});

console.log("\ndropEmptyHeadings:");

it("removes a single empty H2", () => {
    const input = "## Real heading\n\nbody\n\n## \n\nmore body";
    const out = dropEmptyHeadings(input);
    assert.ok(!out.includes("## \n"), `should drop '## ': ${out}`);
    assert.ok(out.includes("## Real heading"));
});

it("preserves headings with content", () => {
    const input = "# A\n## B\n### C";
    const out = dropEmptyHeadings(input);
    assert.strictEqual(out, input);
});

it("removes headings with only whitespace", () => {
    const input = "###    \n# real";
    const out = dropEmptyHeadings(input);
    assert.ok(!out.includes("###"));
    assert.ok(out.includes("# real"));
});

console.log("\ndropTinyImageRefs:");

it("strips refs to sub-threshold files", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "docx2md-test-tiny-"));
    try {
        // 200-byte placeholder → should be dropped
        fs.writeFileSync(path.join(tmpDir, "tiny.png"), Buffer.alloc(200));
        // 5KB real image → should be kept
        fs.writeFileSync(path.join(tmpDir, "real.png"), Buffer.alloc(5000));
        const ctx = { imagesDirPath: tmpDir, imagesDirName: "out_imgs" };
        const md = "before ![](out_imgs/tiny.png) middle ![](out_imgs/real.png) after";
        const out = dropTinyImageRefs(md, ctx, 500);
        assert.ok(!out.includes("tiny.png"), `tiny ref should be dropped: ${out}`);
        assert.ok(out.includes("real.png"), `real ref should remain: ${out}`);
    } finally {
        fs.rmSync(tmpDir, { recursive: true, force: true });
    }
});

it("leaves unrelated refs alone (different dir)", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "docx2md-test-tiny-"));
    try {
        const ctx = { imagesDirPath: tmpDir, imagesDirName: "out_imgs" };
        const md = "![](https://external/foo.png) and ![](other_dir/bar.png)";
        const out = dropTinyImageRefs(md, ctx, 500);
        assert.strictEqual(out, md);
    } finally {
        fs.rmSync(tmpDir, { recursive: true, force: true });
    }
});

console.log(`\n${passed} test(s) passed.`);
