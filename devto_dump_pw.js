const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const c = JSON.parse(fs.readFileSync('outbox/mailtm-devto.json', 'utf8'));
  const b = await chromium.launchPersistentContext('.devto-profile', { headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36' });
  const p = b.pages()[0] || await b.newPage();
  await p.goto('https://dev.to/users/password/new', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(4000);
  const forms = await p.evaluate(() => Array.from(document.querySelectorAll('form')).map(f => ({
    action: f.getAttribute('action'), method: f.getAttribute('method'),
    fields: Array.from(f.querySelectorAll('input,button')).map(i => `${i.tagName}:${i.type}:${i.name||i.id||''}:${(i.value||'').slice(0,14)}`),
  })));
  console.log('  forms: ' + JSON.stringify(forms).slice(0, 900));
  const inputs = await p.evaluate(() => Array.from(document.querySelectorAll('input')).map(i => `${i.type}/${i.name}/${i.id}`));
  console.log('  inputs: ' + JSON.stringify(inputs).slice(0, 500));
  await b.close();
})();
