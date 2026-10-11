// Gumroad の管理画面の実物を見る (どれが製品で、編集口がどの url か、料金 tab が在るか)。
// 買い手頁に Subscribe しか出ない = 販売形態が定期/メンバーシップの可能性。確定させる。
const { chromium } = require('playwright');

(async () => {
  const b = await chromium.launchPersistentContext('.gumroad-profile', {
    headless: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
  });
  const p = b.pages()[0] || await b.newPage();
  const log = (m) => console.log('  ' + m);

  for (const u of ['https://gumroad.com/products', 'https://gumroad.com/dashboard']) {
    await p.goto(u, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await p.waitForTimeout(5000);
    log('=== ' + u + ' → ' + p.url());
    const txt = await p.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));
    log('本文: ' + txt.slice(0, 460));
    const links = await p.evaluate(() => Array.from(document.querySelectorAll('a[href]'))
      .map(a => a.getAttribute('href'))
      .filter(h => h && (/product|edit|installment|membership|workflow/.test(h)))
      .slice(0, 22));
    log('link: ' + JSON.stringify(links));
  }

  // 製品の編集口を探して開く
  const edit = 'https://gumroad.com/l/bopcg/edit';
  await p.goto(edit, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(6000);
  log('=== ' + edit + ' → ' + p.url());
  const tabs = await p.evaluate(() => Array.from(document.querySelectorAll('a,button,[role="tab"]'))
    .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 26).slice(0, 60));
  log('操作語: ' + JSON.stringify(Array.from(new Set(tabs))));
  await p.screenshot({ path: '/tmp/gr_admin.png', fullPage: true });
  await b.close();
})();
