const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".browser-profile"),
    { headless: true, locale: "ja-JP" });
  const page = await ctx.newPage();
  await page.goto("https://note.com", { waitUntil: "domcontentloaded", timeout: 45000 });
  for (const ep of ["/api/v1/memberself", "/api/v2/memberself", "/api/v1/notifications/count"]) {
    const res = await page.evaluate(async (u) => {
      const r = await fetch(u, { credentials: "include" });
      let b = ""; try { b = (await r.text()).slice(0, 200); } catch (e) {}
      return { status: r.status, body: b };
    }, ep);
    console.log(`  ${ep} -> ${res.status}`);
    console.log(`     ${res.body.replace(/\s+/g, " ").slice(0, 170)}`);
  }
  await ctx.close();
})();
