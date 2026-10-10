const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('https://dev.to/enter', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(3000);
  const l = await p.evaluate(() => [...document.querySelectorAll('a,button')]
    .map(x => (x.innerText || '').trim() + ' -> ' + (x.href || (x.closest('form') || {}).action || ''))
    .filter(t => /creat|sign|regist|join/i.test(t)).slice(0, 10));
  console.log(l.map(x => '  ' + x.slice(0, 110)).join('\n'));
  await b.close();
})();
