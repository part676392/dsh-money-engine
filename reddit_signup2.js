const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const M = JSON.parse(fs.readFileSync("outbox/mailtm.json", "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".reddit-profile"), {
    headless: false, locale: "en-US", viewport: { width: 1360, height: 900 },
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
  });
  const p = await ctx.newPage();
  const steps = [];
  await p.goto("https://www.reddit.com/register/", { waitUntil: "load", timeout: 90000 });
  await sleep(9000); // hydrate through the js_challenge
  const snap = async (tag) => {
    const s = await p.evaluate(() => ({
      url: location.href.slice(0, 60),
      fields: [...document.querySelectorAll("input")].map(i => i.name || i.placeholder || i.type),
      buttons: [...document.querySelectorAll("button")].map(b => (b.innerText || "").trim()).filter(Boolean).slice(0, 6),
    })).catch(e => ({ err: e.message.split("\n")[0] }));
    steps.push({ tag, ...s });
    console.log(`  [${tag}] fields=${JSON.stringify(s.fields)} btn=${JSON.stringify(s.buttons)}`);
    return s;
  };
  await snap("initial");

  const email = p.locator('input[name="email"], input[type="email"]').first();
  await email.waitFor({ timeout: 20000 }).catch(() => {});
  if (await email.count()) { await email.fill(M.address); console.log("  email filled"); }
  await p.locator('button:has-text("Continue")').first().click({ timeout: 12000 }).catch(e => console.log("  continue1:", e.message.split("\n")[0]));
  await sleep(6000);
  await snap("after-continue1");

  const u = "CustomScene" + Math.random().toString(36).slice(2, 6);
  const pw = "Sc3ne!" + Date.now().toString().slice(-7);
  for (const [sel, val] of [['input[name="username"]', u], ['input[name="password"]', pw]]) {
    const l = p.locator(sel).first();
    if (await l.count()) { await l.fill(val).catch(() => {}); console.log(`  filled ${sel}`); }
    else console.log(`  MISSING ${sel}`);
  }
  await p.screenshot({ path: "outbox/shots/reddit-b2.png" });
  for (const label of ["Create account", "Sign up", "Continue"]) {
    const b = p.locator(`button:has-text("${label}")`).first();
    if (await b.count()) {
      await b.click({ timeout: 10000 }).then(() => console.log(`  clicked: ${label}`)).catch(e => console.log(`  click ${label}:`, e.message.split("\n")[0]));
      break;
    }
  }
  await sleep(9000);
  const final = await snap("final");
  await p.screenshot({ path: "outbox/shots/reddit-final.png" });
  const body = await p.evaluate(() => document.body.innerText.replace(/\s+/g, " ").slice(0, 300)).catch(() => "");
  console.log("  final text:", body);
  fs.writeFileSync("outbox/reddit-attempt2.json", JSON.stringify({
    tried_at: new Date().toISOString(), username: u, password: pw, email: M.address, steps, finalText: body,
  }, null, 1));
  await ctx.close();
})();
