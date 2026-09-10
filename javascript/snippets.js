// ### ID: js0001 ###
// Title: Extract Scribd document text
// Description: Collect page text from a Scribd document page and print it.
// Tags:
// - javascript
// - browser
// - dom
// - scribd
// Platforms:
// - browser

function get_questions(){
	if (document.URL.startsWith('https://es.scribd.com/document')) {
		const all_questions = [];
		Array.from(document.querySelectorAll('div[id^="page"]')).forEach(item => {
			all_questions.push(item.innerText);
		});
		console.log(all_questions.join(''));
	} else {
		console.error('Invalid URL');
	}
}


// ### ID: js0002 ###
// Title: Parse CVE record
// Description: Extract CVE record details from cve.org and print a Markdown summary.
// Tags:
// - javascript
// - browser
// - dom
// - cve
// - markdown
// Platforms:
// - browser

function parseCveRecord(){
    if (!document.URL.startsWith('https://www.cve.org/CVERecord?id=CVE-')) {
        console.error("Invalid domain. This tool is only usable in 'https://www.cve.org/CVERecord'");
        return;
    } else {
        const cveRecord = {};
        cveRecord.url = document.URL;
        cveRecord.cveId = document.querySelector("#cve-main-page-content").querySelector('h1').innerText;
        cveRecord.cna = document.querySelector("#cve-cna-cve-program-containers").querySelector('button.message-header.cve-accordion-header').innerText.replace('CNA: ', '');
        try {
            cveRecord.cwe = document.querySelector("#cve-cwes").querySelector('div.cve-y-scroll.cve-scroll-box').innerText.replaceAll(/CWE-\d{1,4}[: ]+/gi, '');
        } catch (error) { // use title as cwe
            console.warn("No CWE information found");
            cveRecord.cwe = document.querySelector("#cve-record-title-container").innerText.replace('Title: ', '').replaceAll(cveRecord.product, '').trim(); 
        }
        cveRecord.product = document.querySelectorAll("#cve-vendor-product-platforms p.cve-product-status-heading")[1].nextElementSibling.innerText;
        let md = `- [${cveRecord.cveId}](${cveRecord.url}): ${cveRecord.cwe} in ${cveRecord.product}. Dicovered by ${cveRecord.cna}.`;
        console.log(md);
        return cveRecord;
    }
}


// ### ID: js0003 ###
// Title: Resize Outlook side panel
// Description: Resize the Outlook web side panel to a minimum, maximum, or bounded pixel width.
// Tags:
// - javascript
// - browser
// - dom
// - outlook
// Platforms:
// - browser

function sidepanel_width(width) {
    // Resize outlook sidebar
    const MIN_WIDTH = 235;
    const MAX_WIDTH = 400;
    let _final_width = null;

    if (width.toLowerCase() === 'max') {
        _final_width = MAX_WIDTH;
    } else if (width.toLowerCase() === 'min') {
        _final_width = MIN_WIDTH;
    } else if (width > 400 || width < 235) {
        console.warn("Width out of bounds [235, 400]");
        return;
    }
    document.querySelector('#leftPaneScrollContainer').style.width = `${_final_width}px`;
    console.log(`[+] Side-panel updated: width ${_final_width}px`)
    // TODO: check if I can de it by drag-drop the container edge.
}
