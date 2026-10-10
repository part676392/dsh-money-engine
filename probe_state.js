const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".browser-profile"),
    { headless: true, locale: "ja-JP" });
  const page = await ctx.newPage();
  await page.goto("https://note.com/settings/profile", { waitUntil: "domcontentloaded", timeout: 45000 });
  const text = (await page.evaluate(() => document.body.innerText)).replace(/\s+/g, " ");
  console.log("  URL:", page.url());
  console.log("  本文冒頭 260字:", text.slice(0, 260));
  console.log("  手動ログイン誘導がある:", /ログインしてください|ログインすると|مية ユーザー/.test(text));
  await ctx.close();
})();
