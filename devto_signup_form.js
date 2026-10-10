const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('https://dev.to/enter?signup_subforem=1&state=new-user',
               { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(4000);
  const s = await p.evaluate(() => {
    const fm = [...document.querySelectorAll('form')].find(f => /users/.test(f.action || '') &&
               [...f.querySelectorAll('input')].some(i => (i.name || '').includes('username')));
    return {
      action: fm ? fm.getAttribute('action') : null,
      fields: fm ? [...fm.querySelectorAll('input,select')].map(i => i.type + ':' + (i.name || '?')) : [],
      btn: fm ? [...fm.querySelectorAll('button,input[type=submit]')].map(x => (x.innerText || x.value || '').trim()) : [],
      captcha: /hcaptcha|g-recaptcha|turnstile/i.test(document.documentElement.innerHTML),
      text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 300),
    };
  });
  console.log('  action : ' + s.action);
  console.log('  fields : ' + JSON.stringify(s.fields));
  console.log('  btn    : ' + JSON.stringify(s.btn));
  console.log('  captcha: ' + s.captcha);
  console.log('  text   : ' + s.text);
  await b.close();
})();
