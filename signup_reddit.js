// Reddit の登録を通す. 前に止まった場所を特定して越える.
//
//   前回の記録 (outbox/reddit-attempt2.json): /register に留まり inputs=None。
//   実物は «Continue with Phone Number / Sign in with Apple / Email» の選択頁で、
//   **Email を押してからフォームが出る**。前の計器はそこを押せていなかった。
//   今回は各段で input を列挙し、名前パターンで埋め、画面の文面をそのまま出す。
const { chromium } = require("playwright");
const fs = require("fs");

const cred = JSON.parse(fs.readFileSync("outbox/mailtm-reddit.json", "utf8"));
const USER = process.env.RU || ("dshlab" + Math.random().toString(36).slice(2, 8));
const PW = cred.password;
const PROBLEM = /(already taken|not available|invalid|error|try again|couldn|blocked|too many|verify your)/i;
const VERIFY = /(verify|confirm|check your (e-?mail|inbox)|we sent|verification link)/i;

(async () => {
  const b = await chromium.launch({ headless: true });
  const ctx = await b.newContext({
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    locale: "en-US", viewport: { width: 1280, height: 1000 } });
  const pg = await ctx.newPage();
  const reqs = [];
  pg.on("response", r => { if (/register|signup|api\/web|verify/.test(r.url())) reqs.push(`${r.status()} ${r.url().slice(0, 62)}`); });

  const dump = async (tag) => {
    const inputs = await pg.$$eval("input", els => els.map(e => ({
      id: e.id || "", name: e.name || "", type: e.type || "", ph: e.placeholder || "" }))).catch(() => []);
    const btns = await pg.$$eval("button, a[role=button]", els =>
      els.map(e => (e.innerText || "").trim()).filter(Boolean).slice(0, 10)).catch(() => []);
    const body = (await pg.evaluate(() => document.body.innerText) || "").replace(/\s+/g, " ");
    const cap = await pg.evaluate(() => !!document.querySelector(
      "[class*=captcha],[id*=captcha],iframe[src*=captcha],iframe[src*=challenges],.FWgRYA"));
    console.log(JSON.stringify({ tag, url: pg.url(), inputs: inputs.map(i => i.id || i.name || i.type),
      buttons: btns, captcha: cap, body_head: body.slice(0, 170) }));
    return { inputs, body };
  };

  await pg.goto("https://www.reddit.com/register/", { waitUntil: "domcontentloaded", timeout: 45000 });
  await pg.waitForTimeout(3500);
  await dump("01_initial");

  // 2. «Email» を押してフォームを出す
  for (const sel of ['button:has-text("Email")', 'div[role=button]:has-text("Email")',
                     'button:has-text("Continue with Email")']) {
    const el = await pg.$(sel);
    if (el) { await el.click().catch(() => {}); await pg.waitForTimeout(2500);
      console.log(JSON.stringify({ step: "clicked", sel })); break; }
  }
  await dump("02_after_email");

  // 3. 名前パターンで埋める
  const put = async (sel, val) => {
    const el = await pg.$(sel);
    if (!el) return false;
    await el.click().catch(() => {});
    await el.fill(val).catch(() => {});
    return true;
  };
  const spec = await pg.$$eval("input", els => els.map(e => ({ id: e.id || "", name: e.name || "", type: e.type || "" })))
    .catch(() => []);
  const filled = {};
  for (const f of spec) {
    const key = (f.id || f.name || "").toLowerCase();
    if (!key) continue;
    const sel = f.id ? `#${f.id}` : `[name="${f.name}"]`;
    if (/username|user_name/.test(key)) filled[key] = await put(sel, USER);
    else if (/email/.test(key)) filled[key] = await put(sel, cred.address);
    else if (/password/.test(key)) filled[key] = await put(sel, PW);
  }
  console.log(JSON.stringify({ step: "filled", ...filled, username: USER }));
  await dump("03_filled");

  // 4. «I am human» があれば押す (Reddit の «I am human» チェック。出たら正直に記録する)
  for (const sel of ['button:has-text("I am human")', '[name=remember]', 'input[type=checkbox]']) {
    const el = await pg.$(sel);
    if (el) { await el.click({ force: true }).catch(() => {});
      console.log(JSON.stringify({ step: "human_checkbox", sel })); break; }
  }

  // 5. 提出
  const btn = await pg.$('button[type=submit], button:has-text("Create account"), button:has-text("Sign up")');
  if (btn) { await btn.click().catch(() => {}); await pg.waitForTimeout(9000); }
  const after = await dump("04_after_submit");
  const verdict = VERIFY.test(after.body) ? "VERIFY_EMAIL" : (PROBLEM.test(after.body) ? "PROBLEM" : "UNKNOWN");
  console.log(JSON.stringify({ FINAL: verdict, username: USER, url: pg.url(),
    reqs: reqs.slice(0, 6) }, null, 1));
  fs.writeFileSync("outbox/reddit-signup.json", JSON.stringify({
    at: new Date().toISOString(), username: USER, email: cred.address, verdict,
    url: pg.url(), body: after.body.slice(0, 700), requests: reqs.slice(0, 8) }, null, 1));
  await b.close();
})();
