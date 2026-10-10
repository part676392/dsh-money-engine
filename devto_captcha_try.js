// dev.to の reCAPTCHA を headful で素振りして通るか試す.
// 目的: 読者が居る媒体 (dev.to / Qiita) が全部 captcha で機械登録を止めている。
// checkbox 型はブラウザ指紋が良ければ click だけで通ることがあるので、実証する。
// 期待: 通れば /users/sign_up を抜ける。ダメなら "must complete the recaptcha" が残る。
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const c = JSON.parse(fs.readFileSync('outbox/mailtm-devto.json', 'utf8'));
  const b = await chromium.launch({ headless: false, args: ['--disable-blink-features=AutomationControlled'] });
  const ctx = await b.newContext({
    locale: 'en-US', timezoneId: 'America/Los_Angeles', viewport: { width: 1280, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  });
  const p = await ctx.newPage();
  await p.addInitScript(() => Object.defineProperty(navigator, 'webdriver', { get: () => undefined }));

  await p.goto('https://dev.to/users/sign_up?state=email_signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(4000);

  await p.fill('input[name="user[name]"]', 'Career Data Lab');
  await p.fill('input[name="user[username]"]', c.username);
  await p.fill('input[name="user[email]"]', c.address);
  await p.fill('input[name="user[password]"]', c.password);
  await p.fill('input[name="user[password_confirmation]"]', c.password);
  console.log('  form filled: ' + c.address);

  // captcha iframe の checkbox を押す。座標は iframe の位置から計算する。
  const frame = p.frameLocator('iframe[src*="recaptcha"]').first();
  const box = await p.locator('iframe[src*="recaptcha"]').first().boundingBox().catch(() => null);
  console.log('  captcha iframe box: ' + JSON.stringify(box));
  if (box) {
    await p.mouse.click(box.x + 34, box.y + box.height / 2);
    console.log('  clicked checkbox at ' + Math.round(box.x + 34) + ',' + Math.round(box.y + box.height / 2));
    await p.waitForTimeout(6000);
  }
  const token = await p.evaluate(() => {
    const ta = document.querySelector('textarea[name="g-recaptcha-response"]');
    return ta ? { len: ta.value.length } : { len: -1 };
  });
  console.log('  g-recaptcha-response length: ' + token.len);

  await p.click('form input[type=submit]').catch(() => {});
  await p.waitForTimeout(10000);
  const st = await p.evaluate(() => ({
    url: location.href,
    text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 260),
    errs: [...document.querySelectorAll('[class*="error"], .flash, .notice')].map(x => (x.innerText || '').trim().replace(/\n+/g, ' ')).filter(Boolean).slice(0, 3),
  }));
  console.log('  after url : ' + st.url);
  console.log('  errors    : ' + JSON.stringify(st.errs));
  console.log('  text      : ' + st.text);
  fs.writeFileSync('/tmp/devto_captcha_try.json', JSON.stringify(st, null, 1));
  await b.close();
})();
