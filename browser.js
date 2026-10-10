// note を操作するためのブラウザ-driver.
// 設計の要点: パスワードを君に渡させない。
//   1) headful でウィンドウを出す → 2) 君が一度だけログインする
//   3) プロファイルは workspace に保存されるので、以降の投稿は自動化できる
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const PROFILE = path.join(__dirname, ".browser-profile");
const SHOTS = path.join(__dirname, "outbox", "shots");

async function main() {
  const mode = process.argv[2] || "check"; // check | login
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(PROFILE, { recursive: true });

  console.log(`  launching (${mode}) profile=${PROFILE}`);
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    headless: mode !== "login",
    viewport: { width: 1280, height: 900 },
    locale: "ja-JP",
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
  });
  const page = await ctx.newPage();

  const url =
    mode === "login" ? "https://note.com/login" : "https://note.com/shushoku_career1";
  console.log(`  goto ${url}`);
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  console.log(`  http=${resp && resp.status()} title=${await page.title()}`);

  const shot = path.join(SHOTS, `${mode}-${Date.now()}.png`);
  await page.screenshot({ path: shot, fullPage: false });
  console.log(`  screenshot ${shot}`);

  // ログイン必須かどうかを机械的に確かめる
  const hasLogin = await page
    .locator('a[href*="/login"], input[name="mail"], input[type="password"]')
    .count();
  const own = (await page.content()).includes("shushoku_career1");
  console.log(`  login-form-elements=${hasLogin}  own-page-loaded=${own}`);

  if (mode === "login") {
    console.log("\n  ▶ ウィンドウを開きました。note にログインしてください。");
    console.log("    ログインを検出したら自動でセッションを保存します（最大 12 分）。\n");
    const deadline = Date.now() + 12 * 60 * 1000;
    let loggedIn = false;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 5000));
      try {
        const probes = ["https://note.com/settings/profile", "https://note.com/notice"];
        for (const u of probes) {
          const rp = await page.goto(u, { waitUntil: "domcontentloaded", timeout: 30000 });
          const code = rp && rp.status();
          const finalUrl = page.url();
          const stillLogin = finalUrl.includes("/login");
          console.log(`    probe ${u} -> http=${code} url=${finalUrl.slice(0, 46)}`);
          if (code === 200 && !stillLogin) {
            loggedIn = true;
            break;
          }
        }
      } catch (e) {
        console.log("    probe error:", e.message.split("\n")[0]);
      }
      if (loggedIn) break;
    }
    if (!loggedIn) {
      console.log("  ✗ ログイン未検出。ウィンドウは閉じます。");
    } else {
      console.log("  ✓ ログイン確認");
      await page.screenshot({ path: path.join(SHOTS, "logged-in.png"), fullPage: false });
      const cookies = await ctx.cookies("https://note.com");
      fs.writeFileSync(
        path.join(__dirname, "outbox", "note-session.json"),
        JSON.stringify(
          { checked_at: new Date().toISOString(), count: cookies.length,
            names: cookies.map((c) => c.name) },
          null, 1)
      );
      console.log(`  session retained: ${cookies.length} cookies (値は disk に書いていない)`);
    }
  }
  await ctx.close();
  console.log("  closed");
}

main().catch((e) => {
  console.error("  FAILED:", e.message.split("\n")[0]);
  process.exit(1);
});
