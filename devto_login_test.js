const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const c = JSON.parse(fs.readFileSync('outbox/mailtm-devto.json', 'utf8'));
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('https://dev.to/enter', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(3000);
  await p.fill('input[name="user[email]"]', c.address);
  await p.fill('input[name="user[password]"]', c.password);
  await p.click('form[action="/users/sign_in"] input[type=submit]').catch(async()=>{
    await p.locator('input[type=submit][value="Log in"]').first().click();
  });
  await p.waitForTimeout(9000);
  const st = await p.evaluate(() => ({
    url: location.href,
    text: (document.body.innerText||'').replace(/\n+/g,' | ').slice(0,240),
    avatar: !!document.querySelector('a[data-user-token]'),
  }));
  console.log('  url    : ' + st.url);
  console.log('  avatar : ' + st.avatar + '  (=true ならログイン成功)');
  console.log('  text   : ' + st.text);
  await b.close();
})();
