// test_html2docx_preprocess.test.js — unit tests for q-7.
//
// Mirrors skills/pdf/scripts/tests/test_preprocess.py: synthetic HTML
// inputs → invoke individual preprocessing stage from
// _html2docx_preprocess.js → assert on the resulting DOM. Every stage
// the html2docx walker depends on has at least one positive
// (transformation applied) and one negative (transformation NOT
// applied to a similar-but-distinct shape) test.
//
// Test harness: built-in `node:test` runner + `node:assert/strict`.
// No mocha / jest / chai / Vitest — zero new devDependencies.
// Run: `node tests/test_html2docx_preprocess.test.js`

const test = require('node:test');
const assert = require('node:assert/strict');
const cheerio = require('cheerio');
const pp = require('../_html2docx_preprocess');

const load = (html) => cheerio.load(html, { decodeEntities: true });

// ─────────────────────────────────────────────────────────────────────
// Stage 1: stripChromeButtons
// ─────────────────────────────────────────────────────────────────────

test('stripChromeButtons: aria-label="Copy" exact match removed', () => {
    const $ = load('<button aria-label="Copy">x</button><p>keep</p>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 0);
    assert.match($.html(), /<p>keep<\/p>/);
});

test('stripChromeButtons: known chrome variants ("Copy page", "Copy as Markdown") removed', () => {
    const $ = load('<button aria-label="Copy page">x</button><button aria-label="Copy as Markdown">y</button>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 0);
});

test('stripChromeButtons: substantive button "Copy of contract" PRESERVED (q-7 MED-2)', () => {
    // Pre-q-7 the `aria-label^="Copy "` prefix selector silently shredded
    // substantive labels. Now we require exact match against a known
    // chrome allowlist; "Copy of contract" is content and survives.
    const $ = load('<button aria-label="Copy of contract">go</button>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 1);
    assert.match($('button').text(), /go/);
});

test('stripChromeButtons: substantive Russian button "Копировать договор" PRESERVED', () => {
    // Symmetric coverage for the Russian variant.
    const $ = load('<button aria-label="Копировать договор">ок</button>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 1);
});

test('stripChromeButtons: enumerated chrome ("Copy URL", "Copy command", "Скопировать ссылку") removed', () => {
    const $ = load('<button aria-label="Copy URL">a</button><button aria-label="Copy command">b</button><button aria-label="Скопировать ссылку">c</button>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 0);
});

test('stripChromeButtons: <h2><button>anchor</button>Heading</h2> button removed but heading kept', () => {
    const $ = load('<h2><button>#</button>Section</h2>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 0);
    assert.match($('h2').text(), /Section/);
});

test('stripChromeButtons: button outside any heading NOT stripped (substantive)', () => {
    const $ = load('<form><button>Submit</button></form>');
    pp.stripChromeButtons($);
    assert.equal($('button').length, 1);
});

test('stripChromeButtons: Confluence DC [class*="buttonContainer"] hashed wrapper removed', () => {
    const $ = load('<div class="buttonContainer_xyz123HASH==">Toolbar</div><div>body</div>');
    pp.stripChromeButtons($);
    assert.equal($('.buttonContainer_xyz123HASH\\=\\=').length, 0);
    assert.match($.html(), /body/);
});

test('stripChromeButtons: .headerlink + .octicon-link + .copybtn removed', () => {
    const $ = load('<a class="headerlink">¶</a><a class="octicon-link"></a><button class="copybtn">Copy</button><p>keep</p>');
    pp.stripChromeButtons($);
    assert.equal($('.headerlink, .octicon-link, .copybtn').length, 0);
    assert.match($('p').text(), /keep/);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 2: stripDuplicateAndHiddenChrome
// ─────────────────────────────────────────────────────────────────────

test('stripDuplicateAndHiddenChrome: thead.tableFloatingHeader removed', () => {
    const $ = load('<table><thead class="tableFloatingHeader"><tr><th>dup</th></tr></thead><thead><tr><th>real</th></tr></thead></table>');
    pp.stripDuplicateAndHiddenChrome($);
    assert.equal($('thead').length, 1);
    assert.match($('thead').first().text(), /real/);
});

test('stripDuplicateAndHiddenChrome: [style*="display: none"] removed', () => {
    const $ = load('<div style="color: red; display: none">hidden</div><div>visible</div>');
    pp.stripDuplicateAndHiddenChrome($);
    assert.equal($('div').length, 1);
    assert.match($('div').text(), /visible/);
});

test('stripDuplicateAndHiddenChrome: [class*="print:hidden"] (Tailwind) removed', () => {
    const $ = load('<button class="print:hidden">copy</button><p>keep</p>');
    pp.stripDuplicateAndHiddenChrome($);
    assert.equal($('button').length, 0);
});

test('stripDuplicateAndHiddenChrome: display:flex NOT matched (substring guard)', () => {
    const $ = load('<div style="display: flex">flex</div>');
    pp.stripDuplicateAndHiddenChrome($);
    assert.equal($('div').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 3: stripIconSvgs (the deepest set — 8 rules)
// ─────────────────────────────────────────────────────────────────────

test('stripIconSvgs: aria-hidden="true" removed', () => {
    const $ = load('<svg aria-hidden="true"><path/></svg><p>keep</p>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
    assert.match($.html(), /<p>keep<\/p>/);
});

test('stripIconSvgs: FontAwesome prefix="fas" removed', () => {
    const $ = load('<svg prefix="fas" data-icon="check"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: 50×500 vertical timeline NOT removed (AND-rule, not OR)', () => {
    // One axis ≤ 64 (width=50) but the other (height=500) is content-sized.
    // Rule 3 demands BOTH axes ≤ 64; otherwise this is a tall vertical
    // timeline and must survive.
    const $ = load('<svg width="50" height="500"><line x1="25" y1="0" x2="25" y2="500"/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 1);
});

test('stripIconSvgs: 200×200 content SVG preserved', () => {
    const $ = load('<svg width="200" height="200"><rect/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 1);
});

test('stripIconSvgs: Tailwind size-4 class removed', () => {
    const $ = load('<svg class="size-4"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: Tailwind h-3 + w-3 class removed', () => {
    const $ = load('<svg class="h-3 w-3 text-blue-500"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: inline style:width/height ≤64 removed', () => {
    const $ = load('<svg style="width: 16px; height: 16px"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: inline style with single axis ≤64 NOT removed', () => {
    // Rule 5 requires BOTH style:width AND style:height ≤64 — the regex
    // captures both. With only width set, the AND fails and we keep it.
    const $ = load('<svg style="width: 16px"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 1);
});

test('stripIconSvgs: viewBox-only fallback (Mintlify info pattern) removed', () => {
    const $ = load('<svg viewBox="0 0 20 20" aria-label="Info"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: viewBox 0 0 800 600 (large) NOT removed', () => {
    const $ = load('<svg viewBox="0 0 800 600"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 1);
});

test('stripIconSvgs: gb-icon class (GitBook icon) removed', () => {
    const $ = load('<svg class="gb-icon size-text-base"><path/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: FontAwesome 7 mask kit pattern removed', () => {
    const $ = load('<svg><mask id="m"><image href="data:image/svg+xml,fontawesome..."/></mask></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 0);
});

test('stripIconSvgs: <svg><use href="#sprite-logo"/></svg> sprite NOT removed (no mask)', () => {
    // FontAwesome-7 rule is restricted to <mask>; <use> alone is the standard
    // sprite pattern (legitimately used by logo / illustration sites). The
    // negative case ensures Rule 8 doesn't over-strip.
    const $ = load('<svg><use href="#sprite-logo"/></svg>');
    pp.stripIconSvgs($);
    assert.equal($('svg').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 4: stripInactiveRadixTabs
// ─────────────────────────────────────────────────────────────────────

test('stripInactiveRadixTabs: aria-selected="false" removed', () => {
    const $ = load('<button role="tab" aria-selected="false">TS</button><button role="tab" aria-selected="true">JS</button>');
    pp.stripInactiveRadixTabs($);
    assert.equal($('[role="tab"]').length, 1);
    assert.match($('[role="tab"]').text(), /JS/);
});

test('stripInactiveRadixTabs: data-state="inactive" removed (Headless-UI)', () => {
    const $ = load('<button role="tab" data-state="inactive">A</button><button role="tab" data-state="active">B</button>');
    pp.stripInactiveRadixTabs($);
    assert.equal($('[role="tab"]').length, 1);
    assert.match($('[role="tab"]').text(), /B/);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 5: flattenTableBasedCode (shiki / Fern)
// ─────────────────────────────────────────────────────────────────────

test('flattenTableBasedCode: shiki marker on <pre> flattens table to text lines', () => {
    const html = `<pre class="shiki"><table><tr><td>1</td><td>import os</td></tr><tr><td>2</td><td>x = 1</td></tr></table></pre>`;
    const $ = load(html);
    pp.flattenTableBasedCode($);
    const text = $('pre').text();
    assert.match(text, /import os/);
    assert.match(text, /x = 1/);
    // Newline preserved between rows (was the original failure mode):
    assert.match(text, /import os\nx = 1/);
});

test('flattenTableBasedCode: marker on inner <table> (Fern code-block-line-group)', () => {
    const html = `<pre><table class="code-block-line-group"><tr><td>response = api.post()</td></tr></table></pre>`;
    const $ = load(html);
    pp.flattenTableBasedCode($);
    assert.match($('pre').text(), /response = api\.post\(\)/);
});

test('flattenTableBasedCode: <pre> without code marker NOT flattened (ASCII art preserved)', () => {
    const html = `<pre><table><tr><td>+----+</td><td>|art|</td></tr></table></pre>`;
    const $ = load(html);
    pp.flattenTableBasedCode($);
    // The raw <table> stays inside <pre> since neither <pre> nor <table>
    // carries a code-highlighter marker.
    assert.equal($('pre table').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 6: convertAriaTables
// ─────────────────────────────────────────────────────────────────────

test('convertAriaTables: GitBook role="table" + role="row"/cell → <table>/<tr>/<td>', () => {
    const html = `<div role="table"><div role="row"><div role="cell">a</div><div role="cell">b</div></div></div>`;
    const $ = load(html);
    pp.convertAriaTables($);
    assert.equal($('table').length, 1);
    assert.equal($('tr').length, 1);
    assert.equal($('td').length, 2);
});

test('convertAriaTables: rowgroup with columnheader becomes <thead>; otherwise <tbody>', () => {
    const html = `
        <div role="table">
          <div role="rowgroup"><div role="row"><div role="columnheader">Name</div></div></div>
          <div role="rowgroup"><div role="row"><div role="cell">Alice</div></div></div>
        </div>`;
    const $ = load(html);
    pp.convertAriaTables($);
    assert.equal($('thead').length, 1);
    assert.equal($('tbody').length, 1);
    assert.equal($('th').length, 1);
});

test('convertAriaTables: role-less <div> NOT touched', () => {
    const $ = load('<div>not a table</div>');
    pp.convertAriaTables($);
    assert.equal($('div').length, 1);
    assert.equal($('table').length, 0);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 7: flattenMintlifySteps
// ─────────────────────────────────────────────────────────────────────

test('flattenMintlifySteps: role=list with step-title → <h4>N. Title</h4> + content', () => {
    const html = `
        <div role="list" class="steps">
          <div role="listitem">
            <p data-component-part="step-title">Install</p>
            <div data-component-part="step-content"><p>Run npm install</p></div>
          </div>
          <div role="listitem">
            <p data-component-part="step-title">Configure</p>
            <div data-component-part="step-content"><p>Edit config.json</p></div>
          </div>
        </div>`;
    const $ = load(html);
    pp.flattenMintlifySteps($);
    const h4s = $('h4');
    assert.equal(h4s.length, 2);
    assert.match($(h4s[0]).text(), /1\. Install/);
    assert.match($(h4s[1]).text(), /2\. Configure/);
    assert.match($.html(), /npm install/);
    assert.match($.html(), /Edit config\.json/);
    // The original <div role="list"> must be replaced.
    assert.equal($('[role="list"]').length, 0);
});

test('flattenMintlifySteps: title with inline <code> preserved (uses .html(), not .text())', () => {
    const html = `
        <div role="list">
          <div role="listitem">
            <p data-component-part="step-title">Run <code>npm install</code></p>
            <div data-component-part="step-content"><p>body</p></div>
          </div>
        </div>`;
    const $ = load(html);
    pp.flattenMintlifySteps($);
    assert.match($('h4').html(), /<code>npm install<\/code>/);
});

test('flattenMintlifySteps: step-line + step-number decoration removed', () => {
    const html = `
        <div role="list">
          <div role="listitem">
            <div data-component-part="step-line"></div>
            <div data-component-part="step-number">1</div>
            <p data-component-part="step-title">Title</p>
            <div data-component-part="step-content">body</div>
          </div>
        </div>`;
    const $ = load(html);
    pp.flattenMintlifySteps($);
    assert.equal($('[data-component-part="step-line"]').length, 0);
    assert.equal($('[data-component-part="step-number"]').length, 0);
});

test('flattenMintlifySteps: regular role=list without step-title NOT touched here', () => {
    // Non-Steps ARIA list is left for convertAriaLists to pick up.
    const html = `<div role="list"><div role="listitem">a</div></div>`;
    const $ = load(html);
    pp.flattenMintlifySteps($);
    assert.equal($('[role="list"]').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 8: convertAriaLists
// ─────────────────────────────────────────────────────────────────────

test('convertAriaLists: role="list" + role="listitem" → <ol> + <li>', () => {
    const $ = load('<div role="list"><div role="listitem">one</div><div role="listitem">two</div></div>');
    pp.convertAriaLists($);
    assert.equal($('ol').length, 1);
    assert.equal($('li').length, 2);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 9: unwrapInlineButtons
// ─────────────────────────────────────────────────────────────────────

test('unwrapInlineButtons: <th><button>Header</button></th> → <th>Header</th>', () => {
    const $ = load('<table><thead><tr><th><button class="headerButton">Name</button></th></tr></thead></table>');
    pp.unwrapInlineButtons($);
    assert.equal($('button').length, 0);
    assert.match($('th').text(), /Name/);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 10: stripAriaLandmarks
// ─────────────────────────────────────────────────────────────────────

test('stripAriaLandmarks: role=banner / navigation / search / complementary / contentinfo removed', () => {
    const html = `
        <div role="banner">site header</div>
        <nav role="navigation">menu</nav>
        <div role="complementary">sidebar</div>
        <footer role="contentinfo">footer</footer>
        <div role="search">searchbox</div>
        <main>article</main>`;
    const $ = load(html);
    pp.stripAriaLandmarks($);
    assert.equal($('[role]').length, 0);
    assert.match($('main').text(), /article/);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 11: stripConfluenceChromeIds
// ─────────────────────────────────────────────────────────────────────

test('stripConfluenceChromeIds: #header / #footer / #breadcrumbs / #comments-section removed', () => {
    const html = `
        <div id="header">x</div>
        <div id="footer">y</div>
        <div id="breadcrumbs">z</div>
        <div id="comments-section">c</div>
        <div id="title-heading">title (PRESERVED)</div>
        <div id="content">body</div>`;
    const $ = load(html);
    pp.stripConfluenceChromeIds($);
    assert.equal($('#header, #footer, #breadcrumbs, #comments-section').length, 0);
    assert.equal($('#title-heading').length, 1);
    assert.equal($('#content').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 12 (gated): stripReaderModeChrome
// ─────────────────────────────────────────────────────────────────────

test('stripReaderModeChrome: [class*="reaction"], [class*="post-meta"] removed', () => {
    const html = `
        <article>
          <p>body</p>
          <div class="content__reactions">👍 5</div>
          <div class="post-meta">tags / share / etc.</div>
        </article>`;
    const $ = load(html);
    pp.stripReaderModeChrome($);
    assert.equal($('.content__reactions').length, 0);
    assert.equal($('.post-meta').length, 0);
    assert.match($('article').text(), /body/);
});

test('stripReaderModeChrome: BEM-modifier "tm-page__main_has-sidebar" preserved (sidebar excluded from keyword list)', () => {
    // Habr's MAIN article wrapper has class `tm-page__main_has-sidebar`.
    // The keyword list deliberately excludes the bare "sidebar" — substring
    // match would otherwise eat the article body. Pin the safety guard.
    const $ = load('<div class="tm-page__main_has-sidebar"><p>body</p></div>');
    pp.stripReaderModeChrome($);
    assert.equal($('.tm-page__main_has-sidebar').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 13: wrapInlineCodeBlocks (Prism / Confluence DC)
// ─────────────────────────────────────────────────────────────────────

test('wrapInlineCodeBlocks: <code class="language-py"> without <pre> gets wrapped', () => {
    const $ = load('<div><code class="language-py">print(42)</code></div>');
    pp.wrapInlineCodeBlocks($);
    assert.equal($('pre > code.language-py').length, 1);
});

test('wrapInlineCodeBlocks: <pre><code class="language-py"> NOT double-wrapped', () => {
    const $ = load('<pre><code class="language-py">print(42)</code></pre>');
    pp.wrapInlineCodeBlocks($);
    assert.equal($('pre').length, 1);
    assert.equal($('pre > pre').length, 0);
});

test('wrapInlineCodeBlocks: plain <code> without language- class NOT wrapped', () => {
    const $ = load('<p>see <code>foo()</code> for details</p>');
    pp.wrapInlineCodeBlocks($);
    assert.equal($('pre').length, 0);
    assert.equal($('code').length, 1);
});

test('wrapInlineCodeBlocks: Confluence DC [class*="codeBlockContainer"] hashed wrapper triggers wrap', () => {
    const $ = load('<div class="codeBlockContainer_HASH=="><code>SELECT * FROM t</code></div>');
    pp.wrapInlineCodeBlocks($);
    assert.equal($('pre > code').length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 14: hoistPreFromInlineAncestors
// ─────────────────────────────────────────────────────────────────────

test('hoistPreFromInlineAncestors: <span data-code-lang><pre></pre></span> → <pre> escapes <span>', () => {
    const $ = load('<div><span data-code-lang="sql"><pre>SELECT 1</pre></span></div>');
    pp.hoistPreFromInlineAncestors($);
    // Span gets unwrapped — its children (the <pre>) move up a level.
    assert.equal($('div > pre').length, 1);
    assert.equal($('span').length, 0);
});

test('hoistPreFromInlineAncestors: <pre> already at block level NOT touched', () => {
    const $ = load('<div><pre>code</pre></div>');
    pp.hoistPreFromInlineAncestors($);
    assert.equal($('div > pre').length, 1);
});

test('hoistPreFromInlineAncestors: <pre> nested in <em><strong> — unwraps both inline ancestors', () => {
    const $ = load('<section><em><strong><pre>nested</pre></strong></em></section>');
    pp.hoistPreFromInlineAncestors($);
    assert.equal($('section > pre').length, 1);
    assert.equal($('em').length, 0);
    assert.equal($('strong').length, 0);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 15: flattenTocDoubleNumbering
// ─────────────────────────────────────────────────────────────────────

test('flattenTocDoubleNumbering: .toc-macro ol → ul + .toc-outline removed', () => {
    const $ = load('<div class="toc-macro"><ol><li><span class="toc-outline">3.1</span> Heading</li></ol></div>');
    pp.flattenTocDoubleNumbering($);
    assert.equal($('.toc-macro ol').length, 0);
    assert.equal($('.toc-macro ul').length, 1);
    assert.equal($('.toc-outline').length, 0);
});

// ─────────────────────────────────────────────────────────────────────
// Stage 16: stripConfluenceNamespacedElements
// ─────────────────────────────────────────────────────────────────────

test('stripConfluenceNamespacedElements: <ac:foo> + <ri:bar> stripped, onWarn called once', () => {
    // Real Confluence emits explicit closing tags. Cheerio's HTML parser
    // does NOT honour XML-style self-closing slashes, so unclosed
    // `<ac:macro/>` would absorb every subsequent sibling into its
    // children — not a realistic input shape.
    const html = '<body><ac:macro></ac:macro><ri:page></ri:page><ac:other></ac:other><p>body</p></body>';
    const $ = load(html);
    let warnCount = 0;
    pp.stripConfluenceNamespacedElements($, { onWarn: () => warnCount++ });
    assert.equal(warnCount, 1, 'onWarn fires exactly once regardless of element count');
    assert.match($('p').text(), /body/);
});

test('stripConfluenceNamespacedElements: page with no namespaced elements: zero warns', () => {
    const $ = load('<p>plain</p>');
    let warnCount = 0;
    pp.stripConfluenceNamespacedElements($, { onWarn: () => warnCount++ });
    assert.equal(warnCount, 0);
});

// ─────────────────────────────────────────────────────────────────────
// Orchestrator: preprocessDom
// ─────────────────────────────────────────────────────────────────────

test('preprocessDom: returns originalBodyText (snapshot before reader-mode strip)', () => {
    const html = `
        <body>
          <p>article body that survives</p>
          <div class="reaction">5</div>
        </body>`;
    const $ = load(html);
    const { originalBodyText } = pp.preprocessDom($, { readerMode: true });
    assert.equal(typeof originalBodyText, 'number');
    assert.ok(originalBodyText >= 1, 'originalBodyText is positive');
    // After preprocess + readerMode, the reaction widget is gone:
    assert.equal($('.reaction').length, 0);
});

test('preprocessDom: readerMode=false leaves reader-mode-only widgets in place', () => {
    const html = '<body><p>body</p><div class="post-share">share</div></body>';
    const $ = load(html);
    pp.preprocessDom($, { readerMode: false });
    // Default mode skips reader-mode keyword strip.
    assert.equal($('.post-share').length, 1);
});

test('preprocessDom: onWarn callback wired through to namespaced-element strip', () => {
    const $ = load('<body><ac:macro/><p>hi</p></body>');
    const messages = [];
    pp.preprocessDom($, { readerMode: false, onWarn: (m) => messages.push(m) });
    assert.equal(messages.length, 1);
    assert.match(messages[0], /Confluence-style namespaced/);
});
