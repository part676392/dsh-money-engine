const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".browser-profile"),
    { headless: true, locale: "ja-JP" });
  const page = await ctx.newPage();
  const marks = {};
  for (const [k, url] of Object.entries({
    profile: "https://note.com/settings/profile",
    stat: "https://note.com/mystat",
    editor: "https://note.com/mypage/create",
  })) {
    try {
      const r = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      const html = await page.content();
      marks[k] = {
        http: r && r.status(),
        url: page.url().slice(0, 60),
        logout_link: /ログアウト/.test(html),
        own_handle: html.includes("shushoku_career1"),
        needs_login: /ログインしてください|パスワードが|メールアドレスを入力/.test(html),
      };
    } catch (e) { marks[k] = { error: e.message.split("\n")[0] }; }
  }
  const cookies = await ctx.cookies("https://note.com");
  const names = cookies.map(c => c.name);
  console.log("  auth-ish cookies:", names.filter(n => /sess|token|hatena|uid|member/i.test(n)).join(", ") || "none");
  console.log("  total cookies:", cookies.length);
  console.log(JSON.stringify(marks, null, 1));
  fs.writeFileSync(path.join(__dirname, "outbox", "login-verify.json"),
    JSON.stringify({ checked_at: new Date().toISOString(), cookies: cookies.length, marks }, null, 1));
  await ctx.close();
})();
