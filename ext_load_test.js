const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const ext = "/tmp/ext";
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".ext-profile"), {
    headless: false,
    args: [
      `--disable-extensions-except=${ext}`,
      `--load-extension=${ext}`,
      "--no-first-run",
    ],
    locale: "ja-JP",
  });
  const page = await ctx.newPage();
  let sw = ctx.serviceWorkers();
  if (!sw.length) {
    try { sw = [await ctx.waitForEvent("serviceworker", { timeout: 20000 })]; } catch (e) {}
  }
  console.log(`  service workers attached: ${sw.length}`);
  for (const s of sw) console.log(`    url: ${s.url().slice(0, 80)}`);

  await page.goto("https://www.threads.com/@maruchan_benkyo", {
    waitUntil: "domcontentloaded", timeout: 60000,
  }).catch(e => console.log("  goto:", e.message.split("\n")[0]));
  await page.waitForTimeout(5000);

  const probe = await page.evaluate(() => ({
    title: document.title.slice(0, 50),
    posts: document.querySelectorAll('article').length,
    injected: !!(window.__threadsResearch || window.threadsResearch),
    // content script が仕込んだ UI 要素を探す
    ui: [...document.querySelectorAll("div,button")].filter(n =>
      /スレッズリサーチ|リサーチ|取得/.test(n.textContent || "") && n.children.length < 3
    ).slice(0, 3).map(n => (n.textContent || "").trim().slice(0, 40)),
  })).catch(e => ({ error: e.message.split("\n")[0] }));
  console.log("  page probe:", JSON.stringify(probe, null, 1));
  await ctx.close();
})();
