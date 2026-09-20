/*
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: github
version: 0.1.0
author: octanima-labs
description: Github toolkit
repo: https://github.com/octanima-labs/codepills/blob/main/javascript/github.js
license: MIT
usage: Paste into a browser console in the corresponding github URL
tags:
  - javascript
  - browser
  - dom
  - github
requires:
  - browser DOM
platforms:
  - browser
CODEPILLS-META-END
*/

// Get repo names from GitHub
function getRepoNames() {
    // https://github.com/<OWNER>?tab=repositories
    return Array.from(temp0.querySelectorAll('a[itemprop="name codeRepository"]')).map(e => e.innerText);
}
