function getImages(elem){
    if (elem.querySelectorAll('img') === null){
      return [];
    }
    return Array.from(elem.querySelectorAll('img')).map(e => {
      return `![${e.getAttribute('data-image-title') || e.getAttribute('alt')}](${e.src})`
    })
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
  let article = {}

  article.url = document.URL;
  article.title = document.querySelector('main header').innerText;
  // `[${document.querySelector('aside.w-article-header-comp div.w-author a').innerText}](${document.querySelector('aside.w-article-header-comp div.w-author a').href})`
  article.author = document.querySelector('aside.w-article-header-comp div.w-author a').innerText;
  article.date = new Date(document.querySelector('aside.w-article-header-comp time').getAttribute('datetime')).toISOString().split('T')[0];
  article.tags = Array.from(document.querySelectorAll('ul.article-tags-list a')).map(e => e.innerText.toLowerCase().split(' & ')[0].replaceAll(' ', '-'));
  // https://www.xda-developers.com/${TAG}
  
  article.richContent = Array.from(document.querySelector('#article-body > div.content-block-regular').children).map(e => {
    if(e.tagName === 'P'){
      let _ = e.innerText;
      Array.from(e.querySelectorAll('a')).forEach(e => {
        if (!/(png|jpg|jpeg)$/.test(e.href)){
          _ = _.replace(e.innerText, `[${e.innerText}](${e.href})`);
        }
      });
      Array.from(e.querySelectorAll('code')).forEach(e => {
        _ = _.replace(e.innerText, `\`${e.innerText}\``);
      });
      return [_!==''?_:null, ...getImages(e)];
    } else if (/H\d/.test(e.tagName)){
      return "#".repeat(Number(e.tagName.replace('H', ''))) + ' ' + e.innerText
    } else if (e.tagName === 'DIV' || e.tagName === 'FIGURE'){
      return getImages(e);
    } else if (e.tagName === 'BLOCKQUOTE'){
      return `> ${e.innerText}`
    } else {
      if (!['HR', 'BR'].includes(e.tagName)){
        console.warn(`Unexpected tag ${e.tagName}`)
      }
      return null;
    }
  }).flat().filter(item => item !== null);
  return article;
}

console.log(toMarkdown(parseArticle()));