const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  const r = await p.goto('https://dev.to/enter?signup_subforem=1&state=new-user',
               { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(5000);
  console.log('  http=' + (r ? r.status() : '?') + ' url=' + p.url());
  const all = await p.evaluate(() => ({
    buttons: [...document.querySelectorAll('button')].map(x => (x.innerText||'').trim()).filter(Boolean).slice(0,14),
    submitish: [...document.querySelectorAll('input[type=submit],a[href*="email"]')].map(x => (x.value||x.innerText||'').trim()).filter(Boolean).slice(0,8),
    hasEmailForm: !!document.querySelector('form[action="/users"]'),
    textHead: (document.body.innerText||'').replace(/\n+/g,' | ').slice(0,260),
  }));
  console.log('  buttons   : ' + JSON.stringify(all.buttons));
  console.log('  submitish : ' + JSON.stringify(all.submitish));
  console.log('  emailForm : ' + all.hasEmailForm);
  console.log('  text      : ' + all.textHead);
  await b.close();
})();
