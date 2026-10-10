// 支払いレールの実測を JSON で出す (Gumroad 編).
// curl では "not currently for sale" が見えない。React の water 前だから。
// 同じ過ちを2回割っているので、決済画面の成否は必ずブラウザで見る。
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const g = JSON.parse(fs.readFileSync('outbox/gumroad.json', 'utf8'));
  const url = g.product_url || g.product_slug_url;
  const b = await chromium.launch();
  const ctx = await b.newContext({ locale: 'en-US' });
  const p = await ctx.newPage();
  let http = 0;
  try {
    const r = await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    http = r ? r.status() : 0;
  } catch (e) { http = -1; }
  await p.waitForTimeout(5000);

  const st = await p.evaluate(() => {
    const t = document.body.innerText || '';
    return {
      url: location.href,
      blocked: /not currently for sale/i.test(t),
      price: (t.match(/[¥$][0-9.,]+/g) || []).slice(0, 3),
      buyButtons: [...document.querySelectorAll('button')]
        .map(x => (x.innerText || '').trim())
        .filter(x => /i want this|buy|purchase|pay/i.test(x)).slice(0, 4),
      textLen: t.length,
      text: t.replace(/\n+/g, ' | ').slice(0, 200),
    };
  });

  // 部外者が実際に買えるか: 購入ボタンを押してカード欄まで見る
  let cardStage = { reached: false, hasCardField: false, url: '' };
  const buy = p.locator('button:has-text("I want this"), button:has-text("Buy")').first();
  if (await buy.count()) {
    try {
      await buy.click();
      await p.waitForTimeout(6000);
      cardStage = await p.evaluate(() => ({
        reached: true,
        url: location.href,
        hasCardField: /card number|cvv|expiration|credit card/i.test(document.body.innerText || ''),
      }));
    } catch (e) { cardStage.error = e.message.split('\n')[0]; }
  }

  const out = {
    probed_at: new Date().toISOString(), url, http,
    blocked_by_payout: st.blocked,
    price_shown: st.price,
    buy_buttons: st.buyButtons,
    card_stage: cardStage,
    for_sale: !st.blocked && (st.buyButtons.length > 0 || cardStage.hasCardField),
    text: st.text,
  };
  console.log(JSON.stringify(out, null, 1));
  fs.writeFileSync('/tmp/rail_probe.json', JSON.stringify(out, null, 1));
  await b.close();
})();
