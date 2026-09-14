/*
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: chato-export
version: 1.13.0
author: octanima-labs
description: Export ChatGPT conversations to markdown
repo: https://github.com/octanima-labs/codepills/blob/main/javascript/chato-export.js
license: MIT
usage: Paste into a browser console on a conversation page.
tags:
  - javascript
  - browser
  - dom
requires:
  - browser DOM
platforms:
  - browser
CODEPILLS-META-END
*/

async function getConversation(){
    const DEBUG = true;
    const CHAT_SELECTOR = 'div[class$="_convSearchResultHighlightRoot"]';
    const TEXTBOX_SELECTOR = 'div[data-turn-id-container]';
    const conversationElem = document.querySelector(CHAT_SELECTOR);
    const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    function debug(message, data=null){
        if (!DEBUG){
            return;
        }

        if (data === null){
            console.debug(`[conversation] ${message}`);
        } else {
            console.debug(`[conversation] ${message}`, data);
        }
    }

    async function collectItems(){
        if (conversationElem === null){
            throw new Error(`[conversation] Conversation element not found for selector: ${CHAT_SELECTOR}`);
        }

        const elements = Array.from(conversationElem.querySelectorAll(TEXTBOX_SELECTOR));
        const items = [];

        if (elements.length === 0){
            console.warn(`[conversation] No text elements found for selector: ${TEXTBOX_SELECTOR}`);
        }

        debug('text elements found', elements.length);

        for (const elem of elements){
            elem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await wait(2000);

            const text = elem.innerText.trim();
            debug('collected text', text);
            if (text !== ''){
                items.push({
                    text: text,
                    html: elem.innerHTML.trim()
                });
            }
        }

        return items;
    }

    function cleanMarkdown(text){
        return text
            .replace(/\n{3,}/g, '\n\n')
            .replace(/[ \t]+\n/g, '\n')
            .trim();
    }

    function childrenToMarkdown(node, context={}){
        return Array.from(node.childNodes).map(child => nodeToMarkdown(child, context)).join('');
    }

    function nodeToMarkdown(node, context={}){
        if (node.nodeType === Node.TEXT_NODE){
            return node.textContent;
        }

        if (node.nodeType !== Node.ELEMENT_NODE){
            return '';
        }

        const tagName = node.tagName.toLowerCase();

        if (tagName === 'br'){
            return '\n';
        }

        if (tagName === 'p'){
            return `${childrenToMarkdown(node, context).trim()}\n\n`;
        }

        if (/^h[1-6]$/.test(tagName)){
            return `${'#'.repeat(Number(tagName.replace('h', '')))} ${childrenToMarkdown(node, context).trim()}\n\n`;
        }

        if (tagName === 'strong' || tagName === 'b'){
            return `**${childrenToMarkdown(node, context).trim()}**`;
        }

        if (tagName === 'em' || tagName === 'i'){
            return `*${childrenToMarkdown(node, context).trim()}*`;
        }

        if (tagName === 'code'){
            if (node.parentElement && node.parentElement.tagName.toLowerCase() === 'pre'){
                return node.textContent.trim();
            }
            return `\`${node.textContent}\``;
        }

        if (tagName === 'pre'){
            return parseCodeBlock(node);
        }

        if (tagName === 'a'){
            const text = childrenToMarkdown(node, context).trim() || node.href;
            return node.href ? `[${text}](${node.href})` : text;
        }

        if (tagName === 'img'){
            const alt = node.getAttribute('alt') || '';
            const src = node.getAttribute('src') || '';
            return src ? `![${alt}](${src})` : '';
        }

        if (tagName === 'blockquote'){
            const quote = cleanMarkdown(childrenToMarkdown(node, context));
            return `${quote.split('\n').map(line => `> ${line}`).join('\n')}\n\n`;
        }

        if (tagName === 'ul' || tagName === 'ol'){
            const ordered = tagName === 'ol';
            const items = Array.from(node.children)
                .filter(child => child.tagName.toLowerCase() === 'li')
                .map((child, index) => {
                    const marker = ordered ? `${index + 1}.` : '-';
                    const item = cleanMarkdown(childrenToMarkdown(child, context)).replace(/\n/g, '\n  ');
                    return `${marker} ${item}`;
                });
            return `${items.join('\n')}\n\n`;
        }

        if (tagName === 'li'){
            return childrenToMarkdown(node, context);
        }

        return childrenToMarkdown(node, context);
    }

    function toMarkdown(html){
        const template = document.createElement('template');
        template.innerHTML = html.trim();
        return cleanMarkdown(childrenToMarkdown(template.content));
    }

    function normalizeLanguage(language){
        const aliases = {
            javascript: 'js',
            typescript: 'ts',
            shell: 'bash'
        };
        const normalized = language.toLowerCase();
        return aliases[normalized] || normalized;
    }

    function getLanguageFromText(text){
        const match = String(text || '').match(/(?:language-|lang-|^|\s)(json|javascript|js|typescript|ts|python|bash|shell|html|css|yaml|xml)(?:\s|$)/i);
        return match === null ? '' : normalizeLanguage(match[1]);
    }

    function inferCodeLanguage(code){
        const trimmed = code.trim();

        if (trimmed.startsWith('{') || trimmed.startsWith('[')){
            try {
                JSON.parse(trimmed);
                return 'json';
            } catch (error) {
                return '';
            }
        }

        return '';
    }

    function parseCodeBlock(node){
        const codeElem = node.querySelector('code');
        let code = (codeElem ? codeElem.textContent : node.textContent).trim();
        let language = '';
        const languageSources = [
            codeElem ? codeElem.className : '',
            node.className,
            codeElem ? codeElem.getAttribute('data-language') : '',
            node.getAttribute('data-language'),
            codeElem ? codeElem.getAttribute('aria-label') : '',
            node.getAttribute('aria-label')
        ];

        for (const source of languageSources){
            language = getLanguageFromText(source);
            if (language !== ''){
                break;
            }
        }

        if (language === ''){
            const labelMatch = code.match(/^([A-Z][A-Z0-9+#-]*)\n([\s\S]*)$/);
            if (labelMatch !== null){
                language = normalizeLanguage(labelMatch[1]);
                code = labelMatch[2].trim();
            }
        }

        if (language === ''){
            const inlineLabelMatch = code.match(/^(JSON|JS|JavaScript|TypeScript|TS|Python|Bash|Shell|HTML|CSS|YAML|XML)(?=[{<\[])/i);
            if (inlineLabelMatch !== null){
                language = normalizeLanguage(inlineLabelMatch[1]);
                code = code.slice(inlineLabelMatch[0].length).trim();
            }
        }

        if (language === ''){
            language = inferCodeLanguage(code);
        }

        debug('code block parsed', {
            language: language,
            code: code
        });

        return `\n\n\`\`\`${language}\n${code}\n\`\`\`\n\n`;
    }

    function cleanAnswerMarkdown(markdown){
        return markdown
            .replace(/^\s*#### ChatGPT said:\s*/i, '')
            .trim();
    }

    function parseDatetime(datetimeText){
        const pattern = /^[A-Z][a-z]{2}, ([A-Z][a-z]{2}) (\d{1,2}) at (\d{1,2}):(\d{2}) ([AP]M)$/;
        const monthIndexes = {
            Jan: 0,
            Feb: 1,
            Mar: 2,
            Apr: 3,
            May: 4,
            Jun: 5,
            Jul: 6,
            Aug: 7,
            Sep: 8,
            Oct: 9,
            Nov: 10,
            Dec: 11
        };
        const match = datetimeText.match(pattern);

        if (match === null){
            throw new Error(`Unsupported datetime format: ${datetimeText}`);
        }

        const month = monthIndexes[match[1]];
        if (month === undefined){
            throw new Error(`Unsupported month: ${match[1]}`);
        }

        const year = new Date().getFullYear();
        const day = Number(match[2]);
        let hour = Number(match[3]);
        const minute = Number(match[4]);
        const meridiem = match[5];

        if (meridiem === 'PM' && hour !== 12){
            hour += 12;
        } else if (meridiem === 'AM' && hour === 12){
            hour = 0;
        }

        const date = new Date(year, month, day, hour, minute);
        if (Number.isNaN(date.getTime())){
            throw new Error(`Invalid date after parsing: ${datetimeText}`);
        }

        return date.toISOString();
    }

    function cleanQuestionText(question){
        return normalizeImplicitQuestionLists(question
            .replace(/^You said:\n/, '')
            .replace(/\n\s*\*?Show (more|less)\*?\s*(?:\n\s*\*)?\s*$/i, '')
            .trim()).trim();
    }

    function isImplicitListItem(text){
        return !/[.!?]\s*$/.test(text.trim());
    }

    function normalizeImplicitQuestionLists(question){
        return question.split(/\n{2,}/).map(block => {
            const lines = block.split('\n');
            const output = [];

            for (let i = 0; i < lines.length; i += 1){
                const inlineMatch = lines[i].match(/^(.+?):\s*(\S.*)$/);
                const blockMatch = lines[i].match(/^(.+?):\s*$/);
                const match = inlineMatch || blockMatch;

                if (match === null){
                    output.push(lines[i]);
                    continue;
                }

                const items = inlineMatch === null ? [] : [inlineMatch[2].trim()];
                let j = i + 1;

                while (j < lines.length && lines[j].trim() !== ''){
                    items.push(lines[j].trim());
                    j += 1;
                }

                if (items.length >= 2 && items.every(isImplicitListItem)){
                    debug('implicit question list detected', {
                        mode: inlineMatch === null ? 'block' : 'inline',
                        prefix: match[1].trim(),
                        items: items
                    });
                    output.push(`${match[1].trim()}:`);
                    output.push('');
                    items.forEach(item => output.push(`- ${item}`));
                    i = j - 1;
                } else {
                    output.push(lines[i]);
                }
            }

            return output.join('\n');
        }).join('\n\n');
    }

    function parseQuestion(text, previousTurn=null){
        const datetimePattern = /^([A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2} at \d{1,2}:\d{2} [AP]M)\n/;
        const match = text.match(datetimePattern);
        let datetime = previousTurn ? previousTurn.datetime : null;
        let question = text;

        debug('raw question', text);
        debug('previous datetime', datetime);

        if (match !== null){
            try {
                datetime = parseDatetime(match[1]);
                debug('parsed datetime', { input: match[1], datetime: datetime });
            } catch (error) {
                console.warn('[conversation] Failed to parse question datetime', {
                    input: match[1],
                    text: text,
                    error: error
                });
            }
            question = question.slice(match[0].length);
        } else {
            debug('datetime prefix not found');
        }

        debug('question before cleanup', question);
        question = cleanQuestionText(question);
        debug('cleaned question', question);

        return {
            datetime: datetime,
            question: question
        };
    }

    function toTurns(items){
        const turns = [];

        for (let i = 0; i < items.length; i += 2){
            const parsedQuestion = parseQuestion(items[i].text, turns[turns.length - 1]);
            const answer = items[i + 1] ? cleanAnswerMarkdown(toMarkdown(items[i + 1].html)) : null;

            if (items[i + 1] === undefined){
                console.warn('[conversation] Missing answer for question index', i);
            }

            debug('answer html', items[i + 1] ? items[i + 1].html : null);
            debug('answer markdown', answer);

            turns.push({
                datetime: parsedQuestion.datetime,
                question: parsedQuestion.question,
                answer: answer
            });
        }

        return turns;
    }

    function quoteMarkdown(text){
        return text.split('\n').map(line => `> ${line}`).join('\n');
    }

    function conversationToMarkdown(conversation){
        const heading = `# [${conversation.title}](${conversation.url})`;
        const body = conversation.turns.map((turn, index) => {
            const questionHeading = turn.datetime === null ?
                `## Question ${index + 1}` :
                `## Question ${index + 1} at ${turn.datetime}`;
            const question = quoteMarkdown(turn.question);
            const answer = turn.answer || '';

            return `${questionHeading}\n\n${question}\n\n${answer}\n\n---`;
        }).join('\n\n');

        return `${heading}\n\n${body}`.trim();
    }

    const items = await collectItems();
    const turns = toTurns(items);
    return {
        url: document.URL,
        title: document.title,
        turns: turns,
        toMarkdown: function(){
            return conversationToMarkdown(this);
        }
    };
}

async function copyTextToClipboard(text){
    await navigator.clipboard.writeText(text);
}

function exportPopup(conversation){
    const overlay = document.createElement('div');
    const popup = document.createElement('div');
    const title = document.createElement('h2');
    const message = document.createElement('p');
    const actions = document.createElement('div');
    const copyButton = document.createElement('button');
    const okButton = document.createElement('button');

    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.zIndex = '2147483647';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.background = 'rgba(0, 0, 0, 0.35)';

    popup.style.maxWidth = '420px';
    popup.style.width = 'calc(100% - 32px)';
    popup.style.padding = '20px';
    popup.style.borderRadius = '12px';
    popup.style.background = '#fff';
    popup.style.color = '#111';
    popup.style.boxShadow = '0 18px 60px rgba(0, 0, 0, 0.25)';
    popup.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

    title.textContent = 'Export completed';
    title.style.margin = '0 0 8px';
    title.style.fontSize = '20px';

    message.textContent = 'Conversation parsed and ready to export.';
    message.style.margin = '0 0 16px';

    actions.style.display = 'flex';
    actions.style.gap = '8px';
    actions.style.justifyContent = 'flex-end';

    copyButton.textContent = 'Copy to clipboard';
    okButton.textContent = 'OK';

    [copyButton, okButton].forEach(button => {
        button.style.padding = '8px 12px';
        button.style.border = '1px solid #ccc';
        button.style.borderRadius = '8px';
        button.style.cursor = 'pointer';
        button.style.background = '#f7f7f7';
        button.style.color = '#111';
    });

    copyButton.addEventListener('click', async () => {
        try {
            await copyTextToClipboard(conversation.toMarkdown());
            copyButton.textContent = 'Copied';
        } catch (error) {
            console.warn('[conversation] Failed to copy markdown to clipboard', error);
            copyButton.textContent = 'Copy failed';
        }
    });

    okButton.addEventListener('click', () => {
        overlay.remove();
    });

    actions.append(copyButton, okButton);
    popup.append(title, message, actions);
    overlay.append(popup);
    document.body.append(overlay);
}

async function scrollToPageTop(){
    const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    window.scrollTo({ top: 0, behavior: 'smooth' });

    const startedAt = Date.now();
    while (window.scrollY > 0 && Date.now() - startedAt < 5000){
        await wait(100);
    }

    await wait(500);
}

try {
    let conversation = null;
} catch(SyntaxError) { // Avoid redeclaring the variable
    conversation = null;
}


scrollToPageTop()
    .then(() => getConversation())
    .then(result => {
        conversation = result;
        console.log(conversation);
        exportPopup(conversation);
        return conversation;
    });
