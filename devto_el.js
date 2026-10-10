const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('https://dev.to/enter?signup_subforem=1&state=new-user', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(5000);
  const els = await p.evaluate(() => [...document.querySelectorAll('a,button,input')]
    .filter(x => /sign up with email/i.test((x.innerText || '') + (x.value || '')))
    .map(x => x.outerHTML.slice(0, 260)));
  console.log(els.map(e => '  ' + e).join('\n') || '  ★ 該当要素なし');
  await b.close();
})();
