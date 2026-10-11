// dev.to の垢が死んでいた ("Unable to login" 実測)。mail.tm で受ける password reset を掛ける。
// 垢は agent 自身の物 (個人情報・本名なし)。
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const c = JSON.parse(fs.readFileSync('outbox/mailtm-devto.json', 'utf8'));
  const b = await chromium.launchPersistentContext('.devto-profile', { headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36' });
  const p = b.pages()[0] || await b.newPage();
  const log = (m) => console.log('  ' + m);
  await p.goto('https://dev.to/users/password/new', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(3000);
  log('url: ' + p.url());
  // 検索 form の submit が先にヒットすると click が空振りする (実測で TimeoutError)。
  const FORM = 'form[action="/users/password"] ';
  const email = FORM + 'input[name="user[email]"]';
  const n = await p.locator(email).count();
  log('email field: ' + n);
  if (!n) { log('★ メール欄が無い'); await b.close(); process.exit(2); }
  await p.locator(email).first().fill(c.address);
  const btn = p.locator(FORM + 'input[type="submit"]').first();
  log('submit: ' + (await btn.count()));
  await btn.click();
  await p.waitForTimeout(6000);
  log('after url: ' + p.url());
  const txt = await p.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').slice(0, 260));
  log('after: ' + txt);
  await b.close();
})();
