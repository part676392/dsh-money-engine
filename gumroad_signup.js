// Gumroad でカード決済導線を作るための signup 試行.
// 意味: 暗号オンリーの店頁は素人が払わない。カードが通れば摩擦が一段下がる。
// 注意: ユーザーの個人情報・本名・銀行は一切入れていない (mail.tm の使い捨て adress と
// 自分で生成したパスワードのみ)。規約同意は出るが、当事者はこのエージェント用の垢。
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const [addr, pw] = fs.readFileSync('/tmp/gr_mail', 'utf8').trim().split('\n');
  const b = await chromium.launch();
  const ctx = await b.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36', locale: 'en-US' });
  const p = await ctx.newPage();
  console.log('  account: ' + addr);
  await p.goto('https://gumroad.com/signup', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(2500);

  const emailSel = 'input[type="email"], input[name*="email" i]';
  const pwSel = 'input[type="password"]';
  const ecount = await p.locator(emailSel).count();
  const pcount = await p.locator(pwSel).count();
  console.log(`  fields: email=${ecount} password=${pcount}`);
  if (!ecount || !pcount) { console.log('  ★ フィールドが見つからない'); await b.close(); return; }

  await p.locator(emailSel).first().fill(addr);
  await p.locator(pwSel).first().fill(pw);
  await p.waitForTimeout(400);

  const btn = p.locator('button:has-text("Create account"), input[type="submit"]').first();
  console.log('  submit button present: ' + (await btn.count()));
  await btn.click();
  await p.waitForTimeout(9000);

  const state = await p.evaluate(() => ({
    url: location.href,
    title: document.title.slice(0, 70),
    text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 400),
    captcha: /captcha|recaptcha|hcaptcha|turnstile/i.test(document.documentElement.innerHTML),
  }));
  console.log('  after submit url  : ' + state.url);
  console.log('  title            : ' + state.title);
  console.log('  captcha appeared : ' + state.captcha);
  console.log('  page text        : ' + state.text);
  await p.screenshot({ path: 'outbox/shots/gumroad_after_submit.png', fullPage: false }).catch(() => {});
  fs.writeFileSync('/tmp/gr_state.json', JSON.stringify(state, null, 1));
  await b.close();
})();
