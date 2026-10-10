// 部外者の目で見 poker: Gumroad 製品が本当にカードで買える状態か.
// 所有者ログイン状態だと「Edit product」が出て買えない状態が見えないため、
// 無垢なブラウザで買う。
const { chromium } = require('playwright');

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ locale: 'en-US' });
  const p = await ctx.newPage();
  await p.goto('https://gumroad.com/l/bopcg', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(4500);

  const s = await p.evaluate(() => ({
    url: location.href,
    price: (document.body.innerText.match(/[¥$][0-9.,]+/g) || []).slice(0, 4),
    btns: [...document.querySelectorAll('button, a')].map(x => (x.innerText || '').trim())
      .filter(t => t && t.length < 34).slice(0, 12),
    text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 320),
  }));
  console.log('  final : ' + s.url);
  console.log('  price : ' + JSON.stringify(s.price));
  console.log('  btns  : ' + JSON.stringify(s.btns));
  console.log('  text  : ' + s.text);

  const buy = p.locator('button:has-text("I want this"), button:has-text("Buy now"), button:has-text("Buy")').first();
  if (await buy.count()) {
    await buy.click();
    await p.waitForTimeout(7000);
    const c = await p.evaluate(() => ({
      url: location.href,
      hasCardField: /card number|cvv|expiration|credit card/i.test(document.body.innerText || ''),
      inputs: [...document.querySelectorAll('input')].map(i => i.placeholder || i.name || i.type).slice(0, 12),
      text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 260),
    }));
    console.log('  AFTER BUY url   : ' + c.url);
    console.log('  card field 有無 : ' + c.hasCardField);
    console.log('  inputs          : ' + JSON.stringify(c.inputs));
    console.log('  text            : ' + c.text);
  } else {
    console.log('  ★ buy button not present → not in a purchasable state');
  }
  await b.close();
})();
