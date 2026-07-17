function getImages(elem){
    if (elem.querySelectorAll('img') === null){
        return [];
    }
    return Array.from(elem.querySelectorAll('img')).map(e => {
        return `![${e.getAttribute('data-image-title') || e.getAttribute('alt')}](${e.src})`
    })
}

function parseDate(text){
    return new Date(text).toISOString().split('T')[0];
}

function replaceLink(elem, text=null){
    text = text || elem.innerText;
    Array.from(elem.querySelectorAll('a')).forEach(elem => {
        if (!/(png|jpg|jpeg)$/.test(elem.href)){ // Ignore image links
            text = text.replace(elem.innerText, `[${elem.innerText}](${elem.href})`);
        }
    });
    return text!==''?text:null;
}

function replaceCode(elem, text=null){
    text = text || elem.innerText;
    Array.from(elem.querySelectorAll('code')).forEach(elem => {
        text = text.replace(elem.innerText, `\`${elem.innerText}\``);
    });
    return text!==''?text:null;
}

function replaceLinkAndCode(elem, text=null){
    return replaceCode(elem, replaceLink(elem, text));
}

function toMarkdown(art){
    return [
        "```frontmatter",
        `title: ${art.title}`,
        `author: ${art.author}`,
        `date: ${art.date}`,
        `categories: ${art.categories || []}`,
        `tags: ${art.tags || []}`,
        `url: ${art.url}`,
        "```\n",
        `# ${art.title}\n`,
        art.richContent.join('\n\n')
    ].join('\n');
}

function parseArticle(){
    const articleElem = document.querySelector('#main > article');
    let article = {}

    article.url = document.URL;
    article.title = articleElem.querySelector('h1').innerHTML;
    article.author = `[${articleElem.querySelector('ul.author a').innerText}](${articleElem.querySelector('ul.author a').href})`;
    article.date = parseDate(articleElem.querySelector('div.entry-meta-last a').innerText);

    // from div.entry-footer get: TAGS
    article.categories = Array.from(document.querySelectorAll('footer.entry-footer > span.cat-links > a')).map(e => e.innerText.toLowerCase().replaceAll(' ', '-'));
    article.tags = Array.from(document.querySelectorAll('footer.entry-footer > span.tags-links > a')).map(e => e.innerText.toLowerCase().replaceAll(' ', '-'));

    let relatedArticles = articleElem.querySelector('div.entry-meta-last a').href;
    // let plainContent = document.querySelector('div.entry-content').innerText;

    article.richContent = Array.from(document.querySelector('div.entry-content').children).map(e => {
        if(e.tagName === 'P'){
            return [replaceLinkAndCode(e), ...getImages(e)];
        } else if (/H\d/.test(e.tagName)){
            return `${"#".repeat(Number(e.tagName.replace('H', '')))} ${e.innerText}`
        } else if (e.tagName === 'DIV' || e.tagName === 'FIGURE'){
            return getImages(e);
        } else if (e.tagName === 'BLOCKQUOTE'){
            return `> ${e.innerText}`;
        } else if(e.tagName === 'OL') {
            return replaceLinkAndCode(e, e.innerText.split('\n').map((e, i) => `${i+1}. ${e}`).join('\n'));
        } else if(e.tagName === 'UL') {
            return replaceLinkAndCode(e, e.innerText.split('\n').map(e => `- ${e}`).join('\n'));
        } else {
            if (!['HR', 'BR'].includes(e.tagName)){ console.warn(`Unexpected tag ${e.tagName}`); }
            return null;
        }
    }).flat().filter(item => item !== null);
    return article;
}

console.log(toMarkdown(parseArticle()));


// When click on cat/tag
// href="https://hackaday.com/category/${CAT}"
// href="https://hackaday.com/tag/${TAG}"


