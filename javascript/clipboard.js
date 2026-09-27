/*
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: clipboard
version: 0.3.0
author: octanima-labs
description: Show browser text in a popup and copy it to the clipboard.
repo: https://github.com/octanima-labs/codepills/blob/main/javascript/clipboard.js
license: MIT
usage: Paste into a browser console, then call copy2clipboardPopup(content).
tags:
  - javascript
  - browser
  - clipboard
  - dom
requires:
  - browser DOM
  - navigator.clipboard
platforms:
  - browser
CODEPILLS-META-END
*/

function copy2clipboardPopup(content){
    const text = String(content ?? '');
    const syntaxes = ['text', 'json', 'markdown', 'yaml'];
    const previous = document.querySelector('[data-copy2clipboard-popup]');

    if (previous !== null){
        previous.remove();
    }

    const overlay = document.createElement('div');
    const modal = document.createElement('div');
    const contentHost = document.createElement('div');
    const actions = document.createElement('div');
    const leftActions = document.createElement('div');
    const rightActions = document.createElement('div');
    const syntaxWrap = document.createElement('div');
    const syntaxMenu = document.createElement('div');
    const themeButton = document.createElement('button');
    const syntaxButton = document.createElement('button');
    const copyButton = document.createElement('button');
    const okButton = document.createElement('button');
    let darkTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    let syntax = 'text';
    let currentPalette = null;
    let contentElement = null;

    overlay.setAttribute('data-copy2clipboard-popup', '');
    overlay.setAttribute('role', 'presentation');
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Copy content to clipboard');
    syntaxButton.setAttribute('aria-haspopup', 'listbox');
    syntaxMenu.setAttribute('role', 'listbox');

    Object.assign(overlay.style, {
        position: 'fixed',
        inset: '0',
        zIndex: '2147483647',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        boxSizing: 'border-box',
        padding: '7vh 24px 24px',
        backdropFilter: 'blur(2px)',
        fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    });

    Object.assign(modal.style, {
        width: 'min(920px, 100%)',
        boxSizing: 'border-box',
        padding: '18px',
        borderRadius: '18px',
        boxShadow: '0 24px 80px rgba(15, 23, 42, 0.28)'
    });

    Object.assign(actions.style, {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        marginTop: '14px'
    });

    [leftActions, rightActions].forEach(group => {
        Object.assign(group.style, {
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
        });
    });

    Object.assign(syntaxWrap.style, {
        position: 'relative'
    });

    Object.assign(syntaxMenu.style, {
        position: 'absolute',
        left: '0',
        bottom: 'calc(100% + 8px)',
        zIndex: '1',
        display: 'none',
        minWidth: '128px',
        padding: '6px',
        borderRadius: '12px',
        boxShadow: '0 16px 48px rgba(15, 23, 42, 0.22)'
    });

    [themeButton, syntaxButton, copyButton, okButton].forEach(button => {
        Object.assign(button.style, {
            minWidth: '82px',
            padding: '9px 14px',
            borderRadius: '999px',
            cursor: 'pointer',
            font: '600 14px/1 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
        });
    });

    Object.assign(themeButton.style, {
        minWidth: '42px',
        padding: '9px 12px'
    });

    themeButton.type = 'button';
    syntaxButton.type = 'button';
    copyButton.type = 'button';
    copyButton.textContent = 'Copy';
    okButton.type = 'button';
    okButton.textContent = 'Ok';

    syntaxes.forEach(name => {
        const item = document.createElement('button');
        item.type = 'button';
        item.textContent = name;
        item.setAttribute('role', 'option');
        Object.assign(item.style, {
            display: 'block',
            width: '100%',
            padding: '8px 10px',
            border: '0',
            borderRadius: '8px',
            background: 'transparent',
            cursor: 'pointer',
            textAlign: 'left',
            font: '600 13px/1 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
        });
        item.addEventListener('click', () => {
            syntax = name;
            closeSyntaxMenu();
            renderContent();
            updateSyntaxButton();
            focusContent();
        });
        syntaxMenu.append(item);
    });

    function escapeHtml(value){
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function span(value, color){
        return `<span style="color:${color}">${escapeHtml(value)}</span>`;
    }

    function highlightJson(value){
        let source = value;

        try {
            source = JSON.stringify(JSON.parse(value), null, 2);
        } catch (error) {
            source = value;
        }

        const tokenPattern = /("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"\s*:|"(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|[{}\[\],:])/g;
        let result = '';
        let index = 0;

        source.replace(tokenPattern, (match, offset) => {
            result += escapeHtml(source.slice(index, offset));
            if (/^"/.test(match) && /:\s*$/.test(match)){
                result += span(match, currentPalette.syntaxKey);
            } else if (/^"/.test(match)){
                result += span(match, currentPalette.syntaxString);
            } else if (/true|false/.test(match)){
                result += span(match, currentPalette.syntaxBoolean);
            } else if (/null/.test(match)){
                result += span(match, currentPalette.syntaxNull);
            } else if (/^-?\d/.test(match)){
                result += span(match, currentPalette.syntaxNumber);
            } else {
                result += span(match, currentPalette.syntaxPunctuation);
            }
            index = offset + match.length;
            return match;
        });

        return result + escapeHtml(source.slice(index));
    }

    function highlightMarkdownInline(escaped){
        return escaped
            .replace(/(`[^`]+`)/g, `<span style="color:${currentPalette.syntaxString}">$1</span>`)
            .replace(/(\[[^\]]+\]\([^)]+\))/g, `<span style="color:${currentPalette.syntaxLink}">$1</span>`)
            .replace(/(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g, `<span style="color:${currentPalette.syntaxBoolean}">$1</span>`);
    }

    function highlightMarkdownLine(line){
        const escaped = escapeHtml(line);

        if (/^#{1,6}\s/.test(line)){
            return escaped.replace(/^(#{1,6})(\s.*)$/u, (_, marker, rest) => {
                return `${span(marker, currentPalette.syntaxPunctuation)}<span style="color:${currentPalette.syntaxKey};font-weight:700">${rest}</span>`;
            });
        }
        if (/^\s*>/.test(line)){
            return `<span style="color:${currentPalette.syntaxComment}">${escaped}</span>`;
        }
        if (/^\s*(?:[-*+] |\d+\. )/.test(line)){
            return escaped.replace(/^(\s*(?:[-*+]|\d+\.))(\s.*)$/u, (_, marker, rest) => {
                return `${span(marker, currentPalette.syntaxPunctuation)}${highlightMarkdownInline(rest)}`;
            });
        }

        return highlightMarkdownInline(escaped);
    }

    function highlightMarkdown(value){
        let inFence = false;

        return value.split('\n').map(line => {
            if (/^```/.test(line)){
                inFence = !inFence;
                return `<span style="color:${currentPalette.syntaxPunctuation}">${escapeHtml(line)}</span>`;
            }
            if (inFence){
                return `<span style="color:${currentPalette.syntaxString}">${escapeHtml(line)}</span>`;
            }
            return highlightMarkdownLine(line);
        }).join('\n');
    }

    function highlightYamlLine(line){
        const match = line.match(/^(\s*)(-\s+)?([A-Za-z0-9_.-]+)(\s*:\s*)(.*)$/);

        if (/^\s*#/.test(line)){
            return `<span style="color:${currentPalette.syntaxComment}">${escapeHtml(line)}</span>`;
        }
        if (match !== null){
            const [, indent, listMarker='', key, separator, rest] = match;
            return [
                escapeHtml(indent),
                listMarker ? span(listMarker, currentPalette.syntaxPunctuation) : '',
                span(key, currentPalette.syntaxKey),
                span(separator, currentPalette.syntaxPunctuation),
                highlightYamlValue(rest)
            ].join('');
        }
        const listMatch = line.match(/^(\s*-)(\s.*)$/);
        if (listMatch !== null){
            const [, marker, rest] = listMatch;
            return `${span(marker, currentPalette.syntaxPunctuation)}${highlightYamlValue(rest)}`;
        }
        return escapeHtml(line);
    }

    function highlightYamlValue(value){
        if (/^\s*#/.test(value)){
            return `<span style="color:${currentPalette.syntaxComment}">${escapeHtml(value)}</span>`;
        }
        return escapeHtml(value)
            .replace(/(&quot;[^&]*&quot;|&#39;[^&]*&#39;)/g, `<span style="color:${currentPalette.syntaxString}">$1</span>`)
            .replace(/\b(true|false|yes|no|on|off)\b/gi, `<span style="color:${currentPalette.syntaxBoolean}">$1</span>`)
            .replace(/\b(null|nil|~)\b/gi, `<span style="color:${currentPalette.syntaxNull}">$1</span>`)
            .replace(/\b-?\d+(?:\.\d+)?\b/g, `<span style="color:${currentPalette.syntaxNumber}">$&</span>`);
    }

    function highlightYaml(value){
        return value.split('\n').map(highlightYamlLine).join('\n');
    }

    function highlightedHtml(){
        if (syntax === 'json'){
            return highlightJson(text);
        }
        if (syntax === 'markdown'){
            return highlightMarkdown(text);
        }
        if (syntax === 'yaml'){
            return highlightYaml(text);
        }
        return escapeHtml(text);
    }

    function contentBoxStyle(element){
        Object.assign(element.style, {
            width: '100%',
            height: 'min(58vh, 520px)',
            boxSizing: 'border-box',
            overflow: 'auto',
            padding: '14px',
            borderRadius: '12px',
            outline: 'none',
            background: currentPalette.textareaBackground,
            border: `1px solid ${currentPalette.textareaBorder}`,
            color: currentPalette.textareaColor,
            font: '14px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
            whiteSpace: 'pre-wrap'
        });
    }

    function renderContent(){
        contentHost.replaceChildren();

        if (syntax === 'text'){
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.readOnly = true;
            textarea.style.resize = 'vertical';
            contentBoxStyle(textarea);
            contentElement = textarea;
            contentHost.append(textarea);
            return;
        }

        const pre = document.createElement('pre');
        const code = document.createElement('code');
        pre.tabIndex = 0;
        pre.style.margin = '0';
        contentBoxStyle(pre);
        code.innerHTML = highlightedHtml();
        pre.append(code);
        contentElement = pre;
        contentHost.append(pre);
    }

    function focusContent(){
        if (contentElement === null){
            return;
        }
        contentElement.focus();
        if (contentElement.select){
            contentElement.select();
        }
    }

    function updateSyntaxButton(){
        syntaxButton.textContent = `${syntax} ▾`;
        syntaxButton.setAttribute('aria-label', `Select syntax, current syntax is ${syntax}`);
        Array.from(syntaxMenu.children).forEach(item => {
            item.setAttribute('aria-selected', String(item.textContent === syntax));
            item.style.fontWeight = item.textContent === syntax ? '800' : '600';
        });
    }

    function closeSyntaxMenu(){
        syntaxMenu.style.display = 'none';
        syntaxButton.setAttribute('aria-expanded', 'false');
    }

    function toggleSyntaxMenu(){
        const open = syntaxMenu.style.display !== 'none';
        syntaxMenu.style.display = open ? 'none' : 'block';
        syntaxButton.setAttribute('aria-expanded', String(!open));
    }

    function applyTheme(){
        currentPalette = darkTheme ? {
            overlay: 'rgba(2, 6, 23, 0.72)',
            modalBackground: '#0f172a',
            modalBorder: 'rgba(148, 163, 184, 0.28)',
            textareaBackground: '#020617',
            textareaBorder: '#334155',
            textareaColor: '#e2e8f0',
            buttonBackground: '#1e293b',
            buttonBorder: '#475569',
            buttonColor: '#e2e8f0',
            menuBackground: '#0f172a',
            primaryBackground: '#e2e8f0',
            primaryBorder: '#e2e8f0',
            primaryColor: '#020617',
            syntaxKey: '#93c5fd',
            syntaxString: '#86efac',
            syntaxNumber: '#fbbf24',
            syntaxBoolean: '#c4b5fd',
            syntaxNull: '#fca5a5',
            syntaxPunctuation: '#94a3b8',
            syntaxComment: '#64748b',
            syntaxLink: '#67e8f9',
            nextIcon: '☀',
            nextLabel: 'Switch to light theme'
        } : {
            overlay: 'rgba(15, 23, 42, 0.56)',
            modalBackground: '#ffffff',
            modalBorder: 'rgba(148, 163, 184, 0.35)',
            textareaBackground: '#f8fafc',
            textareaBorder: '#d7dde8',
            textareaColor: '#0f172a',
            buttonBackground: '#ffffff',
            buttonBorder: '#cbd5e1',
            buttonColor: '#0f172a',
            menuBackground: '#ffffff',
            primaryBackground: '#0f172a',
            primaryBorder: '#0f172a',
            primaryColor: '#ffffff',
            syntaxKey: '#1d4ed8',
            syntaxString: '#047857',
            syntaxNumber: '#b45309',
            syntaxBoolean: '#7c3aed',
            syntaxNull: '#dc2626',
            syntaxPunctuation: '#64748b',
            syntaxComment: '#64748b',
            syntaxLink: '#0891b2',
            nextIcon: '☾',
            nextLabel: 'Switch to dark theme'
        };

        overlay.style.background = currentPalette.overlay;
        modal.style.background = currentPalette.modalBackground;
        modal.style.border = `1px solid ${currentPalette.modalBorder}`;
        syntaxMenu.style.background = currentPalette.menuBackground;
        syntaxMenu.style.border = `1px solid ${currentPalette.buttonBorder}`;
        themeButton.textContent = currentPalette.nextIcon;
        themeButton.setAttribute('aria-label', currentPalette.nextLabel);
        themeButton.title = currentPalette.nextLabel;

        [themeButton, syntaxButton, okButton].forEach(button => {
            button.style.background = currentPalette.buttonBackground;
            button.style.border = `1px solid ${currentPalette.buttonBorder}`;
            button.style.color = currentPalette.buttonColor;
        });
        Array.from(syntaxMenu.children).forEach(item => {
            item.style.color = currentPalette.buttonColor;
        });
        copyButton.style.background = currentPalette.primaryBackground;
        copyButton.style.border = `1px solid ${currentPalette.primaryBorder}`;
        copyButton.style.color = currentPalette.primaryColor;
        renderContent();
    }

    function close(){
        document.removeEventListener('click', onDocumentClick);
        document.removeEventListener('keydown', onKeydown);
        overlay.remove();
    }

    function onDocumentClick(event){
        if (!syntaxWrap.contains(event.target)){
            closeSyntaxMenu();
        }
    }

    function onKeydown(event){
        if (event.key === 'Escape'){
            if (syntaxMenu.style.display !== 'none'){
                closeSyntaxMenu();
                return;
            }
            close();
        }
    }

    async function copy(){
        await navigator.clipboard.writeText(text);

        modal.replaceChildren();
        Object.assign(modal.style, {
            padding: '42px 24px',
            textAlign: 'center',
            color: '#15803d',
            font: '700 18px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
        });
        modal.textContent = 'Copied to clipboard!';
        window.setTimeout(close, 2000);
    }

    copyButton.addEventListener('click', () => {
        copy().catch(error => {
            console.error('Unable to copy to clipboard:', error);
        });
    });
    themeButton.addEventListener('click', () => {
        darkTheme = !darkTheme;
        applyTheme();
        focusContent();
    });
    syntaxButton.addEventListener('click', event => {
        event.stopPropagation();
        toggleSyntaxMenu();
    });
    okButton.addEventListener('click', close);
    document.addEventListener('click', onDocumentClick);
    document.addEventListener('keydown', onKeydown);

    updateSyntaxButton();
    applyTheme();
    syntaxWrap.append(syntaxButton, syntaxMenu);
    leftActions.append(themeButton, syntaxWrap);
    rightActions.append(copyButton, okButton);
    actions.append(leftActions, rightActions);
    modal.append(contentHost, actions);
    overlay.append(modal);
    document.body.append(overlay);
    focusContent();
}

globalThis.copy2clipboardPopup = copy2clipboardPopup;
