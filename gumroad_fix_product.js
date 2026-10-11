// Gumroad の製品が『定期購読』になっていて買えない (実測: 買い手頁に Subscribe ボタンだけ /
// 価格 ¥950 /  買い手の「I want it!」が出ない)。これを一回購入に戻して card checkout を出す。
// 使うのはエージェント自身の垢 (.gumroad-profile の session) だけ。銀行・本名は入れていない。
const { chromium } = require('playwright');

(async () => {
  const b = await chromium.launchPersistentContext('.gumroad-profile', {
    headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
  });
  const p = b.pages()[0] || await b.newPage();
  const log = (m) => console.log('  ' + m);

  // 1) 編集頁へ (logged in かを先に確認)
  await p.goto('https://gumroad.com/l/bopcg/edit', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(6000);
  log('url: ' + p.url());
  const title = await p.title();
  log('title: ' + title.slice(0, 70));
  if (/login|sign_in|sign_up/.test(p.url())) {
    log('★ session が切れている (login に飛んだ) → 人手の閘門');
    await b.close();
    process.exit(2);
  }

  const body = await p.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').slice(0, 700));
  log('本文: ' + body.slice(0, 420));

  // 2) 販売形態の語を探す (One-time / Subscription / Membership)
  for (const k of ['One-time', 'one-time', 'Subscription', 'Membership', 'Price', 'Apply']) {
    const n = await p.locator(`text=${k}`).count();
    if (n) log(`  語 "${k}": ${n} 個`);
  }

  // 3) 一回購入を選ぶ
  const one = p.locator('button:has-text("One-time"), [role="tab"]:has-text("One-time"), label:has-text("One-time")').first();
  if (await one.count()) {
    await one.click();
    await p.waitForTimeout(2500);
    log('One-time を押した');
  } else {
    log('One-time の切替が見当たらない');
  }

  // 4) 価格欄を出す (価額 = 950 円)
  const priceBox = p.locator('input[aria-label*="rice"], input[name*="price" i], input[placeholder*="rice"]').first();
  if (await priceBox.count()) {
    const before = await priceBox.inputValue().catch(() => '?');
    await priceBox.fill('950');
    log('price: ' + before + ' → 950');
  } else {
    log('価格欄が見つからない');
  }

  // 5) 通貨を JPY にできるか (出なければ USD のまま許容)
  const cur = p.locator('text=/JPY|Japanese yen/i').first();
  log('JPY 選択: ' + (await cur.count() ? '有' : '無 (USD のまま)'));

  // 6) 保存
  const save = p.locator('button:has-text("Save"), button:has-text("publish")').first();
  if (await save.count()) {
    await save.click();
    await p.waitForTimeout(5000);
    log('save を押した → ' + p.url());
  } else {
    log('★ Save ボタンが無い');
  }
  await p.screenshot({ path: '/tmp/gr_edit.png', fullPage: false });
  await b.close();
})();
