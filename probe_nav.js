const { chromium } = require("playwright");
const path = require("path");
(async () => {
  for (const mode of [" saved-profile ", "fresh"]) {
    const dir = mode === "fresh" ? path.join(__dirname, ".browser-fresh") : path.join(__dirname, ".browser-profile");
    const ctx = await chromium.launchPersistentContext(dir, { headless: true, locale: "ja-JP" });
    const page = await ctx.newPage();
    await page.goto("https://note.com", { waitUntil: "domcontentloaded", timeout: 45000 });
    const nav = (await page.evaluate(() => {
      const h = document.querySelector("header") || document.body;
      return h.innerText;
    })).replace(/\s+/g, " ");
    const has = (t) => nav.includes(t);
    console.log(`\n  [${mode.trim()}]`);
    console.log("   nav:", nav.slice(0, 150));
    for (const t of ["ログイン", "会員登録", "マイページ", "ログアウト", "投稿"]) {
      console.log(`     ${t}: ${has(t)}`);
    }
    await ctx.close();
  }
})();
