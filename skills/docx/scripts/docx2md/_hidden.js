// Hidden text (<w:vanish/>) removal before mammoth.
//
// Word neither displays nor prints a run whose effective `vanish` property is
// on; mammoth 1.12 ignores the property and emits such runs as ordinary text.
// This pass drops them from document.xml, footnotes.xml and endnotes.xml so the
// markdown carries what a reader of the document sees. `--keep-hidden-text`
// in docx2md.js skips the pass.
//
// Effective value, as Word computes it (vanish is a toggle property,
// ECMA-376 §17.7.3):
//   1. The run's own <w:rPr> is absolute: <w:vanish/> hides,
//      <w:vanish w:val="0|false|off"/> shows.
//   2. Styles: the paragraph's style chain (w:pStyle or the default paragraph
//      style, then basedOn) and the run's character style chain (w:rStyle,
//      then basedOn) each give their nearest explicit value, and the two
//      combine by XOR; an explicit false adds nothing to the XOR. So hidden
//      text in a hidden paragraph style shows, and a character style cannot
//      un-hide a hidden paragraph style.
//   3. <w:docDefaults> applies only when neither style chain sets vanish.
// Verified in Microsoft Word for Mac on 19 combinations (2026-10-21).
// LibreOffice's PDF export differs in four of them and is not the reference.
//
// Honest scope:
//   - Table styles are not consulted.
//   - <w:webHidden/> (hidden only in Web Layout; Word prints it, TOC page
//     numbers carry it) and <w:specVanish/> are left alone.
//   - Runs carrying field structure (<w:fldChar>, <w:instrText>) are kept even
//     when hidden, so mammoth's field begin/separate/end tracking stays
//     balanced; the hidden field result text is still dropped.
//   - Word merges a paragraph whose mark is hidden (hidden paragraph style, or
//     vanish in <w:pPr><w:rPr>) into the next one; this pass keeps the two
//     paragraphs apart.
//   - Shape diagrams are extracted from the original file by _shapes.js, so a
//     drawing inside a hidden run still reaches the markdown that way.

const cheerio = require("cheerio");

const OFF_VALUES = new Set(["0", "false", "off"]);
const ON_VALUES = new Set(["1", "true", "on"]);
const FIELD_STRUCTURE = "w\\:fldChar, w\\:instrText";

// true / false when `rPr` (cheerio selection, may be empty) sets vanish, else undefined.
function vanishOf(rPr) {
    const v = rPr.children("w\\:vanish").first();
    if (!v.length) return undefined;
    const val = v.attr("w:val");
    return val == null || !OFF_VALUES.has(val);
}

function buildStyleIndex(stylesXml) {
    const index = {
        paragraph: new Map(),
        character: new Map(),
        defaultParagraph: null,
        docDefault: undefined,
        anyVanish: false,
    };
    if (!stylesXml) return index;
    index.anyVanish = /<w:vanish\b/.test(stylesXml);
    if (!index.anyVanish) return index;
    const $ = cheerio.load(stylesXml, { xmlMode: true, decodeEntities: false });
    index.docDefault = vanishOf($("w\\:docDefaults > w\\:rPrDefault > w\\:rPr").first());
    $("w\\:style").each((_, el) => {
        const s = $(el);
        const map = index[s.attr("w:type")];
        const id = s.attr("w:styleId");
        if (!(map instanceof Map) || !id) return;
        map.set(id, {
            basedOn: s.children("w\\:basedOn").attr("w:val"),
            vanish: vanishOf(s.children("w\\:rPr").first()),
        });
        if (map === index.paragraph && ON_VALUES.has(s.attr("w:default") || "")) {
            index.defaultParagraph = id;
        }
    });
    return index;
}

// Nearest explicit vanish along a basedOn chain; cycle-safe.
function chainVanish(map, id) {
    const seen = new Set();
    while (id && !seen.has(id)) {
        seen.add(id);
        const style = map.get(id);
        if (!style) return undefined;
        if (style.vanish !== undefined) return style.vanish;
        id = style.basedOn;
    }
    return undefined;
}

function isHiddenRun($, run, index) {
    const rPr = $(run).children("w\\:rPr").first();
    const direct = vanishOf(rPr);
    if (direct !== undefined) return direct;
    if (!index.anyVanish) return false;
    const pStyle = $(run).closest("w\\:p").children("w\\:pPr").children("w\\:pStyle").attr("w:val");
    const fromParagraph = chainVanish(index.paragraph, pStyle || index.defaultParagraph);
    const rStyle = rPr.children("w\\:rStyle").attr("w:val");
    const fromCharacter = rStyle ? chainVanish(index.character, rStyle) : undefined;
    if (fromParagraph === undefined && fromCharacter === undefined) return index.docDefault === true;
    return (fromParagraph === true) !== (fromCharacter === true);
}

// Returns { xml, removed }; `xml` is the input string untouched when nothing is removed.
function stripHiddenRunsFromXml(xml, index) {
    if (!xml || (!index.anyVanish && !/<w:vanish\b/.test(xml))) return { xml, removed: 0 };
    const $ = cheerio.load(xml, { xmlMode: true, decodeEntities: false });
    let removed = 0;
    $("w\\:r").each((_, run) => {
        if (!isHiddenRun($, run, index)) return;
        if ($(run).children(FIELD_STRUCTURE).length) return;
        $(run).remove();
        removed += 1;
    });
    return { xml: removed ? $.xml() : xml, removed };
}

// Mutates parts.documentXml / footnotesXml / endnotesXml in place (the shape
// loadDocxParts returns); returns the number of runs removed.
function stripHiddenText(parts) {
    const index = buildStyleIndex(parts.stylesXml);
    let total = 0;
    for (const key of ["documentXml", "footnotesXml", "endnotesXml"]) {
        const { xml, removed } = stripHiddenRunsFromXml(parts[key], index);
        parts[key] = xml;
        total += removed;
    }
    return total;
}

module.exports = {
    buildStyleIndex,
    stripHiddenRunsFromXml,
    stripHiddenText,
};
