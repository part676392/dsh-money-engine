// 注文ボタンの計器を、実ブラウザの実クリックで証明する。
// ページ読込の計数 (home など) は生 curl でも増えるが、注文ボタンの発火は JS を
// 動かさないと増えない。だから「注文が 0 件」が人の無関心なのか計器の故障なのか、
// この 1 本で切り分ける。dev 箱専用 (runner に playwright が無い)。
const { chromium } = require('playwright');

const SITE = 'https://part676392.github.io/dsh-money-engine';
const ABACUS = 'https://abacus.jasoncameron.dev/get/dsh-money-engine/order-click';

async function count() {
  const r = await fetch(ABACUS);
  const j = await r.json().catch(() => ({}));
  return typeof j.value === 'number' ? j.value : null;
}

(async () => {
  const page = await (await chromium.launch()).newPage();
  let clicked = 0;
  let hitURL = '';
  // GitHub へ飛ぶと後続の読みが遅くなるので、遷移は止めて fetch だけ通す。
  await page.route('**/github.com/**', r => { hitURL = r.request().url(); return r.abort(); });
  page.on('request', r => { if (r.url().includes('/hit/dsh-money-engine/')) clicked++; });

  const before = await count();
  await page.goto(SITE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const link = page.locator("a[href*='template=order.yml']").first();
  const n = await page.locator("a[href*='template=order.yml']").count();
  if (!n) {
    console.log('  ★ 注文リンクが無い — 面が壊れている');
    await page.context().browser().close();
    process.exit(1);
  }
  const label = (await link.innerText()).replace(/\s+/g, ' ').trim();
  await link.click({ timeout: 15000 });
  await page.waitForTimeout(3500);        // no-cors fetch が飛ぶ間をあける
  const after = await count();
  await page.context().browser().close();

  const fired = typeof after === 'number' && (before === null || after > before);
  console.log(`  注文リンク ${n} 本 / 押した文面: "${label.slice(0, 40)}"`);
  console.log(`  GitHub 遷移を試みた址: ${hitURL ? hitURL.slice(0, 74) : '(押えていない)'}`);
  console.log(`  order-click 計数: ${before} → ${after}  ${fired ? '発火 OK' : '★ 発火せず'}`);
  console.log(`  ページ内の hit リクエスト数: ${clicked}`);
  process.exit(fired ? 0 : 1);
})();
