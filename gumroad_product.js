// Gumroad にカード決済の通る製品を1件立てる.
// 目的: 店の導線が暗号オンリーのままでは素人が払わない。カードの checkout URL を持つ。
// 入力するのは製品名と価格だけ。個人情報・銀行は入れていない（payout 未接続のまま）。
const { chromium } = require('playwright');
const fs = require('fs');

const NAME = 'Explicit fiction, written to your specification (1,500 words)';
const PRICE = '6';

(async () => {
  const b = await chromium.launchPersistentContext('.gumroad-profile', {
    headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  });
  const p = b.pages()[0] || await b.newPage();
  const log = (m) => console.log('  ' + m);

  await p.goto('https://gumroad.com/products/new?new_category=true', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(5000);

  // 型を選ぶ (Digital product が一番摩擦が少ない)
  const kind = p.locator('button:has-text("Digital product")').first();
  if (await kind.count()) { await kind.click(); await p.waitForTimeout(1500); log('kind: Digital product selected'); }

  const nameBox = p.locator('input[id*="name" i], input[placeholder*="name" i], input[type="text"]').first();
  await nameBox.fill(NAME);
  log('name filled: ' + (await nameBox.inputValue()).slice(0, 40));

  const priceBox = p.locator('input[id*="price" i]').first();
  if (await priceBox.count()) {
    await priceBox.click({ clickCount: 3 });
    await priceBox.fill(PRICE);
    log('price filled: ' + (await priceBox.inputValue()));
  } else { log('★ price field not found'); }

  const next = p.locator('button:has-text("Next:")').first();
  log('next button: ' + (await next.count() ? (await next.innerText()).trim() : 'NONE'));
  await next.click();
  await p.waitForTimeout(8000);
  log('after next url: ' + p.url());

  // Publish を探す
  for (const label of ['Publish', 'Save & continue', 'Publish product', 'Looks good']) {
    const btn = p.locator(`button:has-text("${label}")`).first();
    if (await btn.count()) {
      log('clicking: ' + label);
      await btn.click();
      await p.waitForTimeout(7000);
      log('  url now: ' + p.url());
      break;
    }
  }

  const st = await p.evaluate(() => ({
    url: location.href,
    text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 350),
    links: [...document.querySelectorAll('a')].map(a => a.href).filter(h => /\/p\/|\/l\/|gumroad\.com\/[a-z0-9-]{3,}$/.test(h)).slice(0, 8),
  }));
  log('final url : ' + st.url);
  log('links     : ' + JSON.stringify(st.links));
  log('text      : ' + st.text);
  fs.writeFileSync('/tmp/gr_product.json', JSON.stringify(st, null, 1));
  await p.screenshot({ path: 'outbox/shots/gumroad_product.png' }).catch(() => {});
  await b.close();
})();
