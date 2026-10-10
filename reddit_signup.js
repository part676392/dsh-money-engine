const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const M = JSON.parse(fs.readFileSync("outbox/mailtm.json", "utf8"));
(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".reddit-profile"), {
    headless: true, locale: "en-US", viewport: { width: 1360, height: 900 },
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
  });
  const p = await ctx.newPage();
  console.log("  goto register");
  await p.goto("https://www.reddit.com/register/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await p.waitForTimeout(3500);
  const state = await p.evaluate(() => ({
    url: location.href, title: document.title.slice(0, 40),
    inputs: [...document.querySelectorAll("input")].map(i => i.name || i.type || i.placeholder).slice(0, 10),
    captcha: !!document.querySelector("[id*=captcha], iframe[src*=captcha], faceless"),
    blocked: /whoa there|blocked|access denied/i.test(document.body.innerText.slice(0, 400)),
  }));
  console.log("  page state:", JSON.stringify(state));
  await p.screenshot({ path: "outbox/shots/reddit-1.png" });

  const user = "CustomScene_" + Math.random().toString(36).slice(2, 7);
  const pw = "Sc3ne!" + Date.now().toString().slice(-7);
  async function fill(sel, val) {
    const l = p.locator(sel).first();
    if (await l.count()) { await l.fill(val, { timeout: 6000 }).catch(() => {}); return true; }
    return false;
  }
  const done = {
    user: await fill('input[name="username"]', user),
    email: await fill('input[name="email"]', M.address),
    pass: await fill('input[name="password"]', pw),
  };
  console.log(`  filled: ${JSON.stringify(done)}  username=${user}`);
  await p.screenshot({ path: "outbox/shots/reddit-2.png" });
  const btn = p.locator('button:has-text("Create account"), button[type="submit"]').first();
  if (await btn.count()) { await btn.click({ timeout: 6000 }).catch(e => console.log("  click:", e.message.split("\n")[0])); }
  await p.waitForTimeout(6000);
  const after = await p.evaluate(() => ({
    url: location.href.slice(0, 70),
    text: document.body.innerText.replace(/\s+/g, " ").slice(0, 260),
    captcha: !!document.querySelector("[id*=captcha], iframe[src*=captcha]"),
  }));
  console.log("  after submit:", JSON.stringify(after, null, 1));
  await p.screenshot({ path: "outbox/shots/reddit-3.png" });
  fs.writeFileSync("outbox/reddit-attempt.json", JSON.stringify({
    tried_at: new Date().toISOString(), username: user, password: pw,
    email: M.address, first: state, after,
  }, null, 1));
  await ctx.close();
})();
