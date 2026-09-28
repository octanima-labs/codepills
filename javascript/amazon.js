/*
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: amazon-markdown
version: 1.0.0
author: octanima-labs
description: Extract a canonical Amazon product Markdown link from the browser page.
repo: https://github.com/octanima-labs/codepills/blob/main/javascript/amazon.js
license: MIT
usage: Paste into a browser console on an Amazon product page, then call amazon.getProductUrl().
tags:
  - javascript
  - browser
  - markdown
  - amazon
requires:
  - browser DOM
  - clipboard.js
platforms:
  - browser
CODEPILLS-META-END
*/

globalThis.amazon = globalThis.amazon || (() => {

function getProductUrl(to_clipboard = true){
    const url = document.URL;
    let title = document.title;
    const amazonRegex = /^(https:\/\/(?:www\.)?amazon\.[a-z.]+).*?\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i;
    const match = url.match(amazonRegex);

    if (!match){
        console.error('Not a valid Amazon product URL.');
        return null;
    }

    const cleanUrl = `${match[1]}/dp/${match[2]}`;
    title = title.replace(/^amazon\.[a-z.]+:\s*/i, '');

    if (title.includes(':')){
        title = title.split(':')[0].trim();
    }

    const markdown = `[${title}](${cleanUrl})`;
    console.log(markdown);

    if (to_clipboard){
        if (typeof globalThis.copy2clipboardPopup === 'function'){
            globalThis.copy2clipboardPopup(markdown);
        } else {
            console.warn('clipboard.js is required for clipboard popup output.');
        }
    }

    return markdown;
}

return {
    getProductUrl: getProductUrl
};
})();

globalThis.amazon.getProductUrl();
