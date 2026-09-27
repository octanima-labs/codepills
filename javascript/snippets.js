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


//////////////////////////////////////////////////////////////

/*+======================================================+*/
/*| Timestamp now                                         |*/
/*+======================================================+*/
Date.now()

/*+======================================================+*/
/*| Datetime now                                         |*/
/*+======================================================+*/
new Date(Date.now()).toLocaleString()

/*+======================================================+*/
/*| Reject cookies automatically                         |*/
/*+======================================================+*/
function wastedCookies(rejectManually=false) {
  const elements = Array.from(document.querySelectorAll('div[role="dialog"] input[type="checkbox"]'));
  console.log(`[*] ${elements.length} cookie providers detected 😶‍🌫️`);
  console.log(`[*] Eating unnecessary cookies 🍪...`);
  for (let i = 0; i < elements.length; i++) {
    const e = elements[i];
    e.checked = false;
  }
  console.log(`[+] No cookies left 🫙`);
  if (!rejectManually) {
    document.querySelector('button.fc-button.fc-confirm-choices.fc-primary-button').click();
    console.log(`[+] Choices confirmed automatically ✅`);
  } else {
    console.log(`[*] Now you just need to confirm your choices👇`);
  }
}


/*+======================================================+*/
/*| I promise going to sleep                             |*/
/*+======================================================+*/
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Then to call it (from an async funtion)
await sleep(DELAY);


/*+======================================================+*/
/*| Copy to clipboard                                    |*/
/*+======================================================+*/
const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    alert('JSON copied to clipboard!');
  } catch (err) {
    console.error('Failed to copy: ', err);
    alert('Failed to copy manually. Check console.');
  }
};

//Then to call it, for example, from a button
copyBtn.onclick = () => copyToClipboard(JSON.stringify(results, null, 2));



/*+======================================================+*/
/*| Progress bar in the terminal                         |*/
/*+======================================================+*/
let percentage = 0;
let prevPercentage = 0

for (let i = 0; i < elements.length; i++) {
  const e = elements[i];
  // Do your nasty things here

  // Update Progress
  percentage = Math.floor((i/elements.length) * 100)
  if (percentage > prevPercentage){
    console.log(`${percentage}% (${i}/${elements.length})`);
    prevPercentage = percentage;
  }