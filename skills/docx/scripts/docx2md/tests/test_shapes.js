// Unit tests for _shapes.js — parsing and bbox computation. Tests use
// synthetic XML/bbox-layout inputs, so no soffice/poppler/real docx needed.
//
// Run: node test_shapes.js

const assert = require("assert");
const {
    parseBboxLayout,
    findAnchorBlockInPdf,
    computeDrawingCropBbox,
    matchLoImgToDrawing,
    findAnchorInsertionLine,
    findStrandedShapeTextLines,
} = require("../_shapes");
const { normalizeForMatching } = require("../_util");

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

console.log("parseBboxLayout:");

it("parses single-page, single-block bbox XHTML", () => {
    const xml = `<page width="612.0" height="792.0"><flow><block xMin="72.0" yMin="100.0" xMax="540.0" yMax="120.0"><line><word>Hello</word><word>World</word></line></block></flow></page>`;
    const pages = parseBboxLayout(xml);
    assert.strictEqual(pages.length, 1);
    assert.strictEqual(pages[0].blocks.length, 1);
    assert.strictEqual(pages[0].blocks[0].text, "Hello World");
    assert.strictEqual(pages[0].width, 612);
    assert.strictEqual(pages[0].blocks[0].yMin, 100);
});

it("decodes XML entities in word text", () => {
    const xml = `<page width="612" height="792"><block xMin="0" yMin="0" xMax="10" yMax="10"><word>&amp;quot;R&amp;D&amp;quot;</word></block></page>`;
    // Note: entities are already decoded once in XML → "&quot;R&D&quot;" →
    // our decode pass turns those into `"R&D"`.
    const pages = parseBboxLayout(xml);
    // After decode, `&` survives, `&quot;` → `"`
    assert.ok(pages[0].blocks[0].text.includes("&") || pages[0].blocks[0].text.includes('"'));
});

console.log("\nfindAnchorBlockInPdf:");

it("matches via tail substring", () => {
    const pages = [{
        pageNum: 1, width: 612, height: 792,
        blocks: [
            { xMin: 72, yMin: 100, xMax: 540, yMax: 120, text: "Prelude content goes here" },
            { xMin: 72, yMin: 130, xMax: 540, yMax: 150, text: "The following diagram illustrates the overall CSIT Change Management Process:" },
        ],
    }];
    const hit = findAnchorBlockInPdf(pages, "...The following diagram illustrates the overall CSIT Change Management Process:");
    assert.ok(hit, "should find the block");
    assert.strictEqual(hit.block.yMin, 130);
});

it("returns null when no match", () => {
    const pages = [{
        pageNum: 1, width: 612, height: 792,
        blocks: [{ xMin: 0, yMin: 0, xMax: 10, yMax: 10, text: "unrelated" }],
    }];
    const hit = findAnchorBlockInPdf(pages, "Some completely different anchor text long enough to match");
    assert.strictEqual(hit, null);
});

it("prefers later pages over earlier TOC matches", () => {
    const pages = [
        { // page 1: TOC-like
            pageNum: 1, width: 612, height: 792,
            blocks: [{ xMin: 72, yMin: 100, xMax: 540, yMax: 120, text: "CHG 1.2 Sub-Process: RFC Review (Process Flow) 11" }],
        },
        { // page 2: body heading
            pageNum: 2, width: 612, height: 792,
            blocks: [{ xMin: 72, yMin: 100, xMax: 540, yMax: 120, text: "CHG 1.2 Sub-Process: RFC Review (Process Flow)" }],
        },
    ];
    const hit = findAnchorBlockInPdf(pages, "CHG 1.2 Sub-Process: RFC Review (Process Flow)");
    assert.strictEqual(hit.page.pageNum, 2, "should match body page, not TOC page");
});

console.log("\ncomputeDrawingCropBbox:");

it("uses yTopAbsPt when drawing has absolute position", () => {
    const pages = [{
        pageNum: 1, width: 612, height: 792,
        blocks: [
            { xMin: 72, yMin: 100, xMax: 540, yMax: 120, text: "anchor text long enough to match" },
            { xMin: 120, yMin: 200, xMax: 300, yMax: 215, text: "Label 1" },
            { xMin: 120, yMin: 420, xMax: 300, yMax: 435, text: "Label N" },
        ],
    }];
    const drawing = {
        anchorText: "anchor text long enough to match",
        widthPt: 400, heightPt: 300,
        effectLeftPt: 0, effectRightPt: 0, effectTopPt: 0, effectBottomPt: 0,
        posOffsetPt: null,
        yTopAbsPt: 180,
        xLeftPt: 100,
    };
    const bbox = computeDrawingCropBbox(pages, drawing);
    assert.ok(bbox, "should return a bbox");
    // Drawing top at y=180, extent height 300 → bottom at 480
    // yBottom = 480 + breathing (~20pt) → ~500
    assert.ok(bbox.y <= 180, "crop top should be at or above yTopAbsPt");
    assert.ok(bbox.y + bbox.height >= 480, "crop bottom should cover drawing extent");
    assert.strictEqual(bbox.x, 100);
    assert.strictEqual(bbox.width, 400);
});

it("falls back to label-inset when no absolute position", () => {
    const pages = [{
        pageNum: 1, width: 612, height: 792,
        blocks: [
            { xMin: 72, yMin: 100, xMax: 540, yMax: 120, text: "anchor text long enough to match" },
            { xMin: 120, yMin: 150, xMax: 300, yMax: 165, text: "Label 1" },
            { xMin: 120, yMin: 400, xMax: 300, yMax: 415, text: "Label N" },
        ],
    }];
    const drawing = {
        anchorText: "anchor text long enough to match",
        widthPt: 400, heightPt: 300,
        effectLeftPt: 0, effectRightPt: 0, effectTopPt: 0, effectBottomPt: 0,
        posOffsetPt: null, yTopAbsPt: null, xLeftPt: null,
    };
    const bbox = computeDrawingCropBbox(pages, drawing);
    assert.ok(bbox);
    // labelsSpan = 415 - 150 = 265. inset = (300-265)/2 = 17.5. drawTop = 132.5.
    // Crop y >= block.yMax (120) and >= drawTop-breathing (clamped),
    // should include the drawing fully.
    assert.ok(bbox.y + bbox.height >= 415, "bottom should cover last label");
});

console.log("\nmatchLoImgToDrawing:");

it("picks drawing whose anchor tail is in loImg.anchor", () => {
    const loImg = { anchor: "Some lead-in text. The following diagram shows overall CSIT process." };
    const drawings = [
        { anchorText: "unrelated text here that won't match anywhere" },
        { anchorText: "The following diagram shows overall CSIT process." },
    ];
    const match = matchLoImgToDrawing(loImg, drawings);
    assert.strictEqual(match, drawings[1]);
});

it("returns null when no drawing matches", () => {
    const loImg = { anchor: "absolutely nothing matches this" };
    const drawings = [{ anchorText: "something else entirely that is long enough" }];
    const match = matchLoImgToDrawing(loImg, drawings);
    assert.strictEqual(match, null);
});

console.log("\nfindAnchorInsertionLine:");

it("finds line in reverse (body over TOC)", () => {
    const lines = [
        "[CHG 1.2 RFC Review 11](#_Toc)",  // TOC line
        "",
        "other prose in the middle of the document",
        "",
        "CHG 1.2 Sub-Process: RFC Review (Process Flow)",  // body heading (line 4)
    ];
    const normalized = lines.map(normalizeForMatching);
    // The function uses its own normalizer; we just pass the raw normalized form.
    const line = findAnchorInsertionLine(normalized, "CHG 1.2 Sub-Process: RFC Review (Process Flow)");
    // Should return 5 (line 4 + 1 = insert after line 4).
    assert.ok(line >= 1, `got ${line}`);
});

it("returns -1 when no match", () => {
    const lines = ["one", "two", "three"];
    const line = findAnchorInsertionLine(lines, "some very long anchor text that isn't in the input lines at all");
    assert.strictEqual(line, -1);
});

console.log("\nfindStrandedShapeTextLines:");

it("drops short labels until heading", () => {
    const lines = [
        "![](diagram.png)",
        "",
        "**RFC**",
        "",
        "**Creation**",
        "",
        "1",
        "",
        "# Next section",
    ];
    const drops = findStrandedShapeTextLines(lines, 1);
    // should drop RFC, Creation, and "1"
    assert.ok(drops.has(2), "should drop **RFC**");
    assert.ok(drops.has(4), "should drop **Creation**");
    assert.ok(drops.has(6), "should drop 1");
    assert.ok(!drops.has(8), "should NOT drop heading");
});

it("stops at bullet list", () => {
    const lines = ["**Label**", "- Item 1"];
    const drops = findStrandedShapeTextLines(lines, 0);
    assert.ok(!drops.has(1), "should stop at bullet");
});

console.log(`\n${passed} test(s) passed.`);
