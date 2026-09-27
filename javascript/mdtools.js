/*
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: mdtools
version: 0.3.0
author: octanima-labs
description: Convert browser DOM content to Markdown
repo: https://github.com/octanima-labs/codepills/blob/main/javascript/mdtools.js
license: MIT
usage: Paste into a browser console, then call htmlToMarkdown(element).
tags:
  - javascript
  - browser
  - dom
  - markdown
requires:
  - browser DOM
platforms:
  - browser
CODEPILLS-META-END
*/

/*
mdtools.js converts selected browser DOM content into portable Markdown.

Paste this file into a browser console, then pass any element or fragment-like
node to htmlToMarkdown(). The converter walks child nodes recursively, so callers
can pass a focused element such as a paragraph or a larger container such as an
article body. Unsupported tags are not dropped: their children are still
converted, and the tag is reported through console.warn so page-specific markup
can be noticed during extraction.

Usage:
    const article = document.querySelector('article');
    const markdown = htmlToMarkdown(article);

Shift heading levels when embedding extracted content under another heading:
    const nested = htmlToMarkdown(article, 2); // h1 -> h3, h4 -> h6

Copy a selected page region to the clipboard:
    await navigator.clipboard.writeText(htmlToMarkdown($0));

Run the built-in smoke test in Node from the repository root:
    node -e "const m = require('./javascript/mdtools.js'); m.selfTestHtmlToMarkdown();"
*/

globalThis.mdtools = globalThis.mdtools || (() => {

const MDTOOLS_TEXT_NODE = 3;
const MDTOOLS_ELEMENT_NODE = 1;
const MDTOOLS_DOCUMENT_NODE = 9;
const MDTOOLS_FRAGMENT_NODE = 11;

/**
 * Convert a DOM element, document fragment, or DOM-like node tree to Markdown.
 *
 * The converter supports common Markdown block and inline constructs including
 * headings, paragraphs, separators, emphasis, blockquotes, lists, images,
 * links, autolinks, code, and math. Unknown element tags preserve their child
 * content and emit a console.warn message.
 *
 * @param {Object|null|undefined} element DOM element, document fragment, or a
 *     DOM-like test fixture with nodeType, tagName/nodeName, childNodes, and
 *     textContent fields.
 * @param {number} [shiftTitles=0] Heading level shift. Positive values make
 *     headings lower priority (h1 -> h2), negative values make headings higher
 *     priority (h2 -> h1). Results are clamped between h1 and h6.
 * @returns {string} Trimmed Markdown representation of the node tree.
 *
 * @example
 * const markdown = htmlToMarkdown(document.querySelector('article'));
 *
 * @example
 * // Embed extracted content under an existing h2 by shifting headings down.
 * const markdown = htmlToMarkdown(document.querySelector('main'), 2);
 */
function htmlToMarkdown(element, shiftTitles=0){
    if (element === null || element === undefined){
        return '';
    }

    return cleanMarkdown(nodeToMarkdown(element, {
        root: true,
        listDepth: 0,
        shiftTitles: normalizeHeadingShift(shiftTitles)
    }));
}

/**
 * Normalize Markdown block spacing after recursive rendering.
 *
 * Renderers intentionally return local fragments with trailing newlines. This
 * final pass removes trailing whitespace, collapses excessive blank lines, and
 * trims the whole result for clipboard-friendly output.
 *
 * @param {string} markdown Raw Markdown assembled from node renderers.
 * @returns {string} Normalized Markdown.
 */
function cleanMarkdown(markdown){
    return String(markdown || '')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .split('\n')
        .map(line => line.replace(/[ \t]+$/g, ''))
        .join('\n')
        .trim();
}

function childrenToMarkdown(node, context={}){
    return childNodes(node).map(child => nodeToMarkdown(child, context)).join('');
}

/**
 * Render one DOM node to Markdown.
 *
 * This is the central dispatch function. It uses numeric nodeType constants so
 * the same implementation can run in browsers and in Node self-tests without
 * relying on global browser Node constants.
 *
 * @param {Object} node DOM or DOM-like node to render.
 * @param {Object} [context={}] Rendering context, including inline mode and
 *     heading shift settings propagated through recursive calls.
 * @returns {string} Markdown fragment for the node.
 */
function nodeToMarkdown(node, context={}){
    if (node === null || node === undefined){
        return '';
    }

    if (node.nodeType === MDTOOLS_TEXT_NODE){
        return node.textContent || '';
    }

    if (node.nodeType === MDTOOLS_DOCUMENT_NODE || node.nodeType === MDTOOLS_FRAGMENT_NODE){
        return childrenToMarkdown(node, context);
    }

    if (node.nodeType !== MDTOOLS_ELEMENT_NODE){
        return '';
    }

    const tagName = getTagName(node);

    if (isMathElement(node, tagName)){
        return renderMath(node, context);
    }

    if (isTransparentElement(tagName)){
        if (isTextOnlyElement(node) && !context.inline){
            return renderTextParagraph(node);
        }
        return childrenToMarkdown(node, context);
    }

    if (/^h[1-6]$/.test(tagName)){
        const level = shiftHeadingLevel(Number(tagName.slice(1)), context.shiftTitles || 0);
        return `${'#'.repeat(level)} ${cleanInline(childrenToMarkdown(node, inlineContext(context)))}\n\n`;
    }

    if (tagName === 'p'){
        const text = cleanInline(childrenToMarkdown(node, inlineContext(context)));
        return text === '' ? '' : `${text}\n\n`;
    }

    if (tagName === 'hr'){
        return '---\n\n';
    }

    if (tagName === 'br'){
        return '\n';
    }

    if (tagName === 'strong' || tagName === 'b'){
        return `**${cleanInline(childrenToMarkdown(node, inlineContext(context)))}**`;
    }

    if (tagName === 'em' || tagName === 'i'){
        return `*${cleanInline(childrenToMarkdown(node, inlineContext(context)))}*`;
    }

    if (tagName === 'blockquote'){
        return renderBlockquote(node, context);
    }

    if (tagName === 'ul' || tagName === 'ol'){
        return renderList(node, tagName === 'ol', context);
    }

    if (tagName === 'li'){
        return cleanMarkdown(childrenToMarkdown(node, context));
    }

    if (tagName === 'pre'){
        return renderCodeBlock(node);
    }

    if (tagName === 'code'){
        if (getTagName(node.parentElement || node.parentNode) === 'pre'){
            return textContent(node);
        }
        return renderInlineCode(textContent(node));
    }

    if (tagName === 'a'){
        return renderLink(node, inlineContext(context));
    }

    if (tagName === 'img'){
        return renderImage(node);
    }

    console.warn(`[mdtools] Unsupported tag: ${tagName || 'unknown'}`);
    if (isTextOnlyElement(node) && !context.inline){
        return renderTextParagraph(node);
    }
    return childrenToMarkdown(node, context);
}

function inlineContext(context){
    return {
        ...context,
        inline: true
    };
}

/**
 * Convert a caller-provided heading shift to a finite integer.
 *
 * @param {*} shiftTitles User-provided heading shift value.
 * @returns {number} Integer shift amount, or 0 for invalid values.
 */
function normalizeHeadingShift(shiftTitles){
    const shift = Number(shiftTitles);
    return Number.isFinite(shift) ? Math.trunc(shift) : 0;
}

/**
 * Apply a heading shift while keeping Markdown heading levels valid.
 *
 * @param {number} level Original HTML heading level from 1 through 6.
 * @param {number} shiftTitles Integer heading shift amount.
 * @returns {number} Shifted heading level clamped between 1 and 6.
 */
function shiftHeadingLevel(level, shiftTitles){
    return Math.min(6, Math.max(1, level + shiftTitles));
}

function isTextOnlyElement(node){
    return childNodes(node).length > 0 &&
        elementChildren(node).length === 0 &&
        textContent(node).trim() !== '';
}

function renderTextParagraph(node){
    const text = cleanInline(textContent(node));
    return text === '' ? '' : `${text}\n\n`;
}

function cleanInline(markdown){
    return String(markdown || '')
        .replace(/[ \t\n]+/g, ' ')
        .trim();
}

function childNodes(node){
    return Array.from(node && node.childNodes ? node.childNodes : []);
}

function elementChildren(node){
    if (node && node.children){
        return Array.from(node.children);
    }
    return childNodes(node).filter(child => child.nodeType === MDTOOLS_ELEMENT_NODE);
}

function getTagName(node){
    if (!node){
        return '';
    }
    return String(node.tagName || node.nodeName || '').toLowerCase();
}

function getAttribute(node, name){
    if (!node){
        return '';
    }
    if (typeof node.getAttribute === 'function'){
        const value = node.getAttribute(name);
        return value === null || value === undefined ? '' : String(value);
    }
    if (node.attributes && Object.prototype.hasOwnProperty.call(node.attributes, name)){
        return String(node.attributes[name]);
    }
    return '';
}

function textContent(node){
    if (!node){
        return '';
    }
    if (node.textContent !== undefined){
        return String(node.textContent);
    }
    return childNodes(node).map(textContent).join('');
}

function classText(node){
    return String(getAttribute(node, 'class') || node.className || '').toLowerCase();
}

function isTransparentElement(tagName){
    return [
        'article', 'body', 'div', 'main', 'section', 'span',
        'header', 'footer', 'nav', 'aside', 'figure', 'figcaption'
    ].includes(tagName);
}

/**
 * Render a blockquote, preserving nested quote depth from recursive output.
 *
 * @param {Object} node Blockquote element or DOM-like node.
 * @param {Object} context Rendering context passed to child nodes.
 * @returns {string} Markdown blockquote fragment.
 */
function renderBlockquote(node, context){
    const quote = cleanMarkdown(childrenToMarkdown(node, context));
    if (quote === ''){
        return '';
    }
    return quote.split('\n').map(line => line === '' ? '>' : `> ${line}`).join('\n') + '\n\n';
}

/**
 * Render an ordered or unordered list and its direct list-item children.
 *
 * @param {Object} node List element or DOM-like node.
 * @param {boolean} ordered Whether to use ordered list markers.
 * @param {Object} context Rendering context passed to list items.
 * @returns {string} Markdown list fragment.
 */
function renderList(node, ordered, context){
    const start = Number(getAttribute(node, 'start') || '1');
    const items = elementChildren(node)
        .filter(child => getTagName(child) === 'li')
        .map((item, index) => renderListItem(item, ordered, start + index, context));

    return items.length === 0 ? '' : `${items.join('\n')}\n\n`;
}

/**
 * Render one list item, including nested child lists.
 *
 * Nested lists are rendered separately from the item's inline/block content so
 * continuation indentation stays stable for both ordered and unordered markers.
 *
 * @param {Object} node List item element or DOM-like node.
 * @param {boolean} ordered Whether the parent list is ordered.
 * @param {number} number Number to use for ordered list markers.
 * @param {Object} context Rendering context passed to child nodes.
 * @returns {string} Markdown list-item fragment without parent trailing blank line.
 */
function renderListItem(node, ordered, number, context){
    const marker = ordered ? `${number}.` : '-';
    const continuationIndent = ' '.repeat(marker.length + 1);
    const nestedIndent = '  ';
    const contentParts = [];
    const nestedParts = [];

    for (const child of childNodes(node)){
        const tagName = getTagName(child);
        if (child.nodeType === MDTOOLS_ELEMENT_NODE && (tagName === 'ul' || tagName === 'ol')){
            nestedParts.push(cleanMarkdown(nodeToMarkdown(child, {
                ...context,
                listDepth: (context.listDepth || 0) + 1
            })));
        } else {
            contentParts.push(nodeToMarkdown(child, context));
        }
    }

    const content = cleanMarkdown(contentParts.join(''));
    const lines = content === '' ? [''] : content.split('\n');
    let output = `${marker} ${lines[0]}`;

    for (let i = 1; i < lines.length; i += 1){
        output += `\n${continuationIndent}${lines[i]}`;
    }

    for (const nested of nestedParts.filter(part => part !== '')){
        output += '\n' + nested.split('\n').map(line => `${nestedIndent}${line}`).join('\n');
    }

    return output;
}

/**
 * Render preformatted content as a fenced Markdown code block.
 *
 * The fence grows when the code itself contains triple backticks so the output
 * remains valid Markdown. Language labels are inferred from common class and
 * data attributes when present.
 *
 * @param {Object} node pre element or DOM-like node.
 * @returns {string} Markdown fenced code block.
 */
function renderCodeBlock(node){
    const codeNode = findFirst(node, child => getTagName(child) === 'code');
    const code = textContent(codeNode || node).replace(/^\n+|\n+$/g, '');
    const language = detectCodeLanguage(codeNode || node);
    const fence = longestBacktickRun(code) >= 3 ? '`'.repeat(longestBacktickRun(code) + 1) : '```';

    return `\n\n${fence}${language}\n${code}\n${fence}\n\n`;
}

function detectCodeLanguage(node){
    const sources = [
        getAttribute(node, 'data-language'),
        getAttribute(node, 'lang'),
        getAttribute(node, 'class'),
        node ? node.className : ''
    ];

    for (const source of sources){
        const match = String(source || '').match(/(?:language-|lang-)?([a-z0-9_+#.-]+)/i);
        if (match !== null && match[1]){
            return normalizeLanguage(match[1]);
        }
    }

    return '';
}

function normalizeLanguage(language){
    const aliases = {
        javascript: 'js',
        typescript: 'ts',
        shell: 'bash'
    };
    const normalized = String(language || '').toLowerCase();
    return aliases[normalized] || normalized;
}

function renderInlineCode(code){
    const ticks = '`'.repeat(longestBacktickRun(code) + 1);
    const padding = code.startsWith(' ') || code.endsWith(' ') || code.includes('`') ? ' ' : '';
    return `${ticks}${padding}${code}${padding}${ticks}`;
}

function longestBacktickRun(text){
    const matches = String(text || '').match(/`+/g) || [''];
    return Math.max(...matches.map(match => match.length));
}

/**
 * Render an anchor as a named Markdown link or an angle-bracket autolink.
 *
 * Relative href values are resolved against the document/page base URL before
 * rendering so the resulting Markdown link is portable outside the source page.
 *
 * @param {Object} node Anchor element or DOM-like node.
 * @param {Object} context Inline rendering context for the anchor text.
 * @returns {string} Markdown link, autolink, or plain text when href is absent.
 */
function renderLink(node, context){
    const href = resolveLinkHref(node);
    const text = cleanInline(childrenToMarkdown(node, context)) || href;

    if (href === ''){
        return text;
    }

    if (text === href){
        return `<${href}>`;
    }

    if (href === `mailto:${text}`){
        return `<${text}>`;
    }

    return `[${text}](${href})`;
}

/**
 * Resolve an anchor href into the value that should be emitted in Markdown.
 *
 * Absolute URLs, protocols, mailto links, and fragment-only links are preserved.
 * Relative URLs are resolved against ownerDocument.baseURI, document.baseURI, or
 * location.href when available.
 *
 * @param {Object} node Anchor element or DOM-like node.
 * @returns {string} Resolved href, original href when resolution is impossible,
 *     or an empty string when the anchor has no href.
 */
function resolveLinkHref(node){
    const rawHref = getAttribute(node, 'href') || node.href || '';
    if (rawHref === ''){
        return '';
    }

    if (/^(?:[a-z][a-z0-9+.-]*:|#)/i.test(rawHref)){
        return rawHref;
    }

    const base = getBaseUrl(node);
    if (base === ''){
        return rawHref;
    }

    try {
        return new URL(rawHref, base).href;
    } catch (error) {
        return rawHref;
    }
}

function getBaseUrl(node){
    if (node && node.ownerDocument && node.ownerDocument.baseURI){
        return node.ownerDocument.baseURI;
    }

    if (typeof document !== 'undefined' && document.baseURI){
        return document.baseURI;
    }

    if (typeof location !== 'undefined' && location.href){
        return location.href;
    }

    return '';
}

function renderImage(node){
    const src = getAttribute(node, 'src') || node.src || '';
    const alt = getAttribute(node, 'alt') || '';
    return src === '' ? '' : `![${alt}](${src})`;
}

function isMathElement(node, tagName){
    if (['math', 'semantics', 'annotation'].includes(tagName)){
        return true;
    }

    if (getMathSourceFromAttributes(node) !== ''){
        return true;
    }

    const className = classText(node);
    return /\b(katex|mathjax|math|tex)\b/.test(className);
}

/**
 * Render browser math markup as inline or block Markdown math.
 *
 * Math source is read from explicit data attributes first, then TeX annotations
 * used by renderers such as KaTeX or MathJax, then text content as a fallback.
 *
 * @param {Object} node Math-related element or DOM-like node.
 * @returns {string} Markdown math fragment.
 */
function renderMath(node){
    const source = getMathSource(node);
    if (source === ''){
        return '';
    }

    if (isBlockMath(node)){
        return `\n\n$$\n${source}\n$$\n\n`;
    }

    return `$${source}$`;
}

/**
 * Extract the best available TeX/math source from a rendered math node.
 *
 * @param {Object} node Math-related element or DOM-like node.
 * @returns {string} Math source text, or an empty string when unavailable.
 */
function getMathSource(node){
    const attributeSource = getMathSourceFromAttributes(node);
    if (attributeSource !== ''){
        return attributeSource;
    }

    const annotation = findMathAnnotation(node);
    if (annotation !== null){
        return textContent(annotation).trim();
    }

    return textContent(node).trim();
}

function getMathSourceFromAttributes(node){
    for (const name of ['data-tex', 'data-latex', 'data-math']){
        const value = getAttribute(node, name).trim();
        if (value !== ''){
            return value;
        }
    }
    return '';
}

function findMathAnnotation(node){
    return findFirst(node, child => {
        if (getTagName(child) !== 'annotation'){
            return false;
        }
        const encoding = getAttribute(child, 'encoding').toLowerCase();
        return encoding.includes('tex') || encoding.includes('latex');
    });
}

function isBlockMath(node){
    const display = [
        getAttribute(node, 'display'),
        getAttribute(node, 'data-display'),
        getAttribute(node, 'mode')
    ].join(' ').toLowerCase();
    const classes = classText(node);
    return /\b(block|display|display-mode)\b/.test(`${display} ${classes}`) || display.includes('true');
}

function findFirst(node, predicate){
    for (const child of childNodes(node)){
        if (child.nodeType === MDTOOLS_ELEMENT_NODE && predicate(child)){
            return child;
        }
        const nested = findFirst(child, predicate);
        if (nested !== null){
            return nested;
        }
    }
    return null;
}

/**
 * Run a dependency-free smoke test for the DOM-to-Markdown converter.
 *
 * The test builds minimal DOM-like objects instead of using document or
 * DOMParser, which keeps it runnable in plain Node. It throws when conversion
 * output or unsupported-tag warnings differ from the expected behavior.
 *
 * @throws {Error} When an assertion fails.
 *
 * @example
 * const mdtools = require('./javascript/mdtools.js');
 * mdtools.selfTestHtmlToMarkdown();
 */
function selfTestHtmlToMarkdown(){
    const warnings = [];
    const originalWarn = console.warn;
    console.warn = function(message){
        warnings.push(String(message));
    };

    try {
        const fixture = elem('div', {}, [
            elem('h1', {}, ['Title']),
            elem('p', {}, [
                'A ', elem('strong', {}, ['bold']), ' and ', elem('em', {}, ['italic']), ' ',
                elem('code', {}, ['x`y']), ' ', elem('a', { href: 'https://example.com' }, ['Example']), ' ',
                elem('a', { href: 'https://example.org' }, ['https://example.org']), ' ',
                elem('a', { href: '/some/url' }, ['Relative']), ' ',
                elem('img', { alt: 'Alt', src: 'image.png' }, [])
            ]),
            elem('hr', {}, []),
            elem('blockquote', {}, [
                elem('p', {}, ['Quote']),
                elem('blockquote', {}, [elem('p', {}, ['Nested'])])
            ]),
            elem('ul', {}, [
                elem('li', {}, ['One']),
                elem('li', {}, ['Two', elem('ol', {}, [elem('li', {}, ['Nested'])])])
            ]),
            elem('pre', {}, [elem('code', { class: 'language-js' }, ['const x = 1;'])]),
            elem('span', { 'data-tex': 'a^2+b^2=c^2' }, []),
            elem('span', { class: 'katex display' }, [
                elem('annotation', { encoding: 'application/x-tex' }, ['\\int_0^1 x dx'])
            ]),
            elem('p', {}, [elem('math', {}, ['x+y'])]),
            elem('section', {}, ['Section text']),
            elem('custom-text', {}, ['Loose text']),
            elem('custom-box', {}, [elem('p', {}, ['Custom content'])])
        ]);

        const expected = [
            '# Title',
            '',
            'A **bold** and *italic* `` x`y `` [Example](https://example.com) <https://example.org> [Relative](https://example.test/some/url) ![Alt](image.png)',
            '',
            '---',
            '',
            '> Quote',
            '>',
            '> > Nested',
            '',
            '- One',
            '- Two',
            '  1. Nested',
            '',
            '```js',
            'const x = 1;',
            '```',
            '',
            '$a^2+b^2=c^2$',
            '',
            '$$',
            '\\int_0^1 x dx',
            '$$',
            '',
            '$x+y$',
            '',
            'Section text',
            '',
            'Loose text',
            '',
            'Custom content'
        ].join('\n');

        const actual = htmlToMarkdown(fixture);
        assertEqual(actual, expected, 'htmlToMarkdown fixture output');
        assertEqual(warnings.length, 2, 'unsupported tag warning count');
        assertEqual(warnings[0], '[mdtools] Unsupported tag: custom-text', 'unsupported text-only tag warning text');
        assertEqual(warnings[1], '[mdtools] Unsupported tag: custom-box', 'unsupported wrapper tag warning text');

        const headings = elem('div', {}, [
            elem('h1', {}, ['One']),
            elem('h2', {}, ['Two']),
            elem('h3', {}, ['Three']),
            elem('h4', {}, ['Four']),
            elem('h5', {}, ['Five']),
            elem('h6', {}, ['Six'])
        ]);

        assertEqual(htmlToMarkdown(headings), [
            '# One',
            '',
            '## Two',
            '',
            '### Three',
            '',
            '#### Four',
            '',
            '##### Five',
            '',
            '###### Six'
        ].join('\n'), 'default heading levels');

        assertEqual(htmlToMarkdown(headings, 2), [
            '### One',
            '',
            '#### Two',
            '',
            '##### Three',
            '',
            '###### Four',
            '',
            '###### Five',
            '',
            '###### Six'
        ].join('\n'), 'positive heading shift');

        assertEqual(htmlToMarkdown(headings, -1), [
            '# One',
            '',
            '# Two',
            '',
            '## Three',
            '',
            '### Four',
            '',
            '#### Five',
            '',
            '##### Six'
        ].join('\n'), 'negative heading shift');
    } finally {
        console.warn = originalWarn;
    }
}

function assertEqual(actual, expected, label){
    if (actual !== expected){
        throw new Error(`${label} mismatch\nExpected:\n${expected}\n\nActual:\n${actual}`);
    }
}

function elem(tagName, attributes={}, children=[]){
    const node = {
        nodeType: MDTOOLS_ELEMENT_NODE,
        tagName: tagName.toUpperCase(),
        nodeName: tagName.toUpperCase(),
        attributes: attributes,
        childNodes: [],
        children: [],
        parentNode: null,
        parentElement: null,
        ownerDocument: { baseURI: 'https://example.test/base/page.html' },
        className: attributes.class || '',
        href: attributes.href || '',
        src: attributes.src || '',
        getAttribute: function(name){
            return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
        }
    };

    for (const child of children){
        const childNode = typeof child === 'string' ? text(child) : child;
        childNode.parentNode = node;
        childNode.parentElement = node;
        childNode.ownerDocument = node.ownerDocument;
        node.childNodes.push(childNode);
        if (childNode.nodeType === MDTOOLS_ELEMENT_NODE){
            node.children.push(childNode);
        }
    }

    Object.defineProperty(node, 'textContent', {
        get: function(){
            return this.childNodes.map(child => child.textContent || '').join('');
        }
    });

    return node;
}

function text(value){
    return {
        nodeType: MDTOOLS_TEXT_NODE,
        textContent: value,
        childNodes: []
    };
}

return {
    htmlToMarkdown: htmlToMarkdown,
    selfTestHtmlToMarkdown: selfTestHtmlToMarkdown
};
})();

if (typeof globalThis !== 'undefined'){
    globalThis.htmlToMarkdown = globalThis.mdtools.htmlToMarkdown;
    globalThis.selfTestHtmlToMarkdown = globalThis.mdtools.selfTestHtmlToMarkdown;
}

if (typeof module !== 'undefined' && module.exports){
    module.exports = globalThis.mdtools;
}
