// dev.to に mail.tm で垢を作る。captcha が本当に記入を止めるかをobjectIdで見る。
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const c = JSON.parse(fs.readFileSync('outbox/mailtm-devto.json', 'utf8'));
  const b = await chromium.launch();
  const ctx = await b.newContext({ locale: 'en-US' });
  const p = await ctx.newPage();
  // /enter の "Sign up with Email" は <a href="/users/sign_up?state=email_signup">
  // だった (実測 outerHTML)。遠回りせず直 URL に飛ぶ。
  await p.goto('https://dev.to/users/sign_up?state=email_signup',
               { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(4000);
  console.log('  on page: ' + p.url());

  const widget = await p.evaluate(() => {
    const w = document.querySelector('.h-captcha, [class*="captcha"], iframe[title*="captcha" i]');
    return w ? { present: true, visible: !!(w.offsetWidth || w.offsetHeight), tag: w.tagName + '.' + (w.className || '').slice(0, 40) } : { present: false };
  });
  console.log('  captcha widget: ' + JSON.stringify(widget));

  await p.fill('input[name="user[name]"]', 'Career Data Lab');
  await p.fill('input[name="user[username]"]', c.username);
  await p.fill('input[name="user[email]"]', c.address);
  await p.fill('input[name="user[password]"]', c.password);
  await p.fill('input[name="user[password_confirmation]"]', c.password);
  console.log('  filled: ' + c.username + ' / ' + c.address);
  await p.click('input[type="submit"][name="commit"], button:has-text("Sign up")').catch(async () => {
    await p.locator('form[action="/users"] input[type=submit]').first().click();
  });
  await p.waitForTimeout(9000);
  const st = await p.evaluate(() => ({
    url: location.href, title: document.title.slice(0, 60),
    errs: [...document.querySelectorAll('.notice, [class*="error"], .flash')].map(x => (x.innerText || '').trim().replace(/\n+/g, ' ')).filter(Boolean).slice(0, 4),
    text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 240),
  }));
  console.log('  after url   : ' + st.url);
  console.log('  title       : ' + st.title);
  console.log('  errors      : ' + JSON.stringify(st.errs));
  console.log('  text        : ' + st.text);
  fs.writeFileSync('/tmp/devto_state.json', JSON.stringify(st, null, 1));
  await ctx.close(); await b.close();
})();
