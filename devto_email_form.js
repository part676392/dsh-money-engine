const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('https://dev.to/enter?signup_subforem=1&state=new-user',
               { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(3500);
  const btn = p.locator('button:has-text("Sign up with Email"), a:has-text("Sign up with Email")').first();
  console.log('  email btn found: ' + (await btn.count()));
  if (await btn.count()) { await btn.click(); await p.waitForTimeout(3500); }
  const s = await p.evaluate(() => ({
    url: location.href,
    forms: [...document.querySelectorAll('form')].map(fm => ({
      action: fm.getAttribute('action'),
      fields: [...fm.querySelectorAll('input')].map(i => i.type + ':' + (i.name || '?')).slice(0, 9),
      btn: [...fm.querySelectorAll('button,input[type=submit]')].map(x => (x.innerText || x.value || '').trim()).slice(0, 2),
    })).filter(f => /users|sign/.test((f.action || '') + JSON.stringify(f.fields))),
    captcha: /hcaptcha|g-recaptcha|turnstile/i.test(document.documentElement.innerHTML),
  }));
  console.log('  forms: ' + JSON.stringify(s.forms, null, 1).slice(0, 900));
  console.log('  captcha: ' + s.captcha);
  await b.close();
})();
