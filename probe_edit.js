const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launchPersistentContext('.gumroad-profile', { headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36' });
  const p = b.pages()[0] || await b.newPage();
  const log = (m) => console.log('  ' + m);
  await p.goto('https://gumroad.com/products/bopcg/edit', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(7000);
  log('url: ' + p.url());
  const txt = await p.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));
  log('本文: ' + txt.slice(0, 1200));
  const inputs = await p.evaluate(() => Array.from(document.querySelectorAll('input,select,textarea')).slice(0,40).map(e =>
    `${e.tagName}:${e.type||''}:${(e.getAttribute('aria-label')||e.name||e.placeholder||'').slice(0,26)}:${(e.value||'').slice(0,18)}`));
  log('field: ' + JSON.stringify(inputs, null, 0).slice(0, 1500));
  await p.screenshot({ path: '/tmp/gr_edit2.png', fullPage: true });
  await b.close();
})();
