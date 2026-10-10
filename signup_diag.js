// 登録が進まない理由を、画面とJSの証拠で特定する (推測しない)。
const { chromium } = require("playwright");
const fs = require("fs");
const cred = JSON.parse(fs.readFileSync("outbox/mailtm-mastodon.json", "utf8"));
const HOST = process.argv[2] || "mastodon.social";
const USER = "dsh_lab_" + Math.random().toString(36).slice(2, 8);

(async () => {
  const b = await chromium.launch({ headless: true });
  const ctx = await b.newContext({ userAgent:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    locale: "en-US", viewport: { width: 1280, height: 1000 } });
  const pg = await ctx.newPage();
  const cons = [], reqs = [];
  pg.on("console", m => { if (/error|warn/i.test(m.type())) cons.push(m.text().slice(0, 120)); });
  pg.on("request", r => { if (/sign_up|accounts|users/.test(r.url())) reqs.push(`${r.method()} ${r.url().slice(0,70)}`); });
  pg.on("response", async r => { if (/sign_up|accounts/.test(r.url())) reqs.push(`-> ${r.status()} ${r.url().slice(0,60)}`); });

  await pg.goto(`https://${HOST}/auth/sign_up`, { waitUntil: "domcontentloaded", timeout: 45000 });
  await pg.waitForTimeout(2500);
  // rules accept
  const acc = await pg.$('button:has-text("Accept"), button[type=submit]');
  if (acc) { await acc.click(); await pg.waitForTimeout(4000); }

  const state = async (tag) => {
    const s = await pg.$$eval("input, select", els => els.map(e => ({
      id: e.id || e.name || "?", tag: e.tagName, type: e.type || "",
      value: e.tagName === "SELECT" ? "sel:" + (e.value || "-") : (e.value ? e.value.slice(0, 18) : "-"),
      invalid: e.getAttribute("aria-invalid") || "", required: e.required || false })));
    console.log(JSON.stringify({ tag, fields: s }));
    const hints = await pg.$$eval(".field_with_errors, [class*=error], .hint, .warning, [role=alert]",
      els => els.map(e => (e.innerText || "").trim()).filter(Boolean).slice(0, 8)).catch(() => []);
    console.log(JSON.stringify({ tag, hints }));
  };
  await state("before_fill");

  const put = async (sel, val) => { const el = await pg.$(sel); if (!el) return false;
    await el.click().catch(()=>{}); await el.fill(val).catch(()=>{}); return true; };
  const filled = {};
  for (const [sel, val] of [["#user_account_attributes_username", USER], ["#user_email", cred.address],
                            ["#user_password", cred.password], ["#user_password_confirmation", cred.password],
                            ["#user_confirm_password", cred.password],
                            ["#user_website", "https://part676392.github.io/dsh-money-engine"]]) {
    filled[sel] = await put(sel, val);
  }
  for (const [sel, v] of [["#user_date_of_birth_1i", "1990"], ["#user_date_of_birth_2i", "6"], ["#user_date_of_birth_3i", "15"]]) {
    const el = await pg.$(sel);
    if (el) { const ok = await pg.selectOption(sel, { value: v }).then(()=>true).catch(()=>false);
      let alt = null;
      if (!ok) alt = await pg.$$eval(sel, e => Array.from(e[0].options).slice(0,4).map(o=>o.value)).catch(()=>[]);
      filled[sel] = ok ? v : ("FAIL opts=" + JSON.stringify(alt)); }
    else filled[sel] = "no element";
  }
  const cb = await pg.$('input[type=checkbox]');
  if (cb) await cb.check({ force: true }).catch(() => {});
  console.log(JSON.stringify({ filled }));
  await state("after_fill");

  const btn = await pg.$('button[type=submit], button:has-text("Sign up"), button:has-text("Create")');
  const info = btn ? { text: (await btn.innerText().catch(()=> "")).trim(), disabled: await btn.isDisabled().catch(()=>null) } : null;
  console.log(JSON.stringify({ submit_button: info }));
  await btn.click().catch(e => console.log(JSON.stringify({ click_err: String(e).slice(0,120) })));
  await pg.waitForTimeout(8000);
  await state("after_submit");
  const body = (await pg.evaluate(() => document.body.innerText) || "").replace(/\s+/g, " ");
  console.log(JSON.stringify({ url: pg.url(), body_head: body.slice(0, 700) }));
  console.log(JSON.stringify({ console_errors: cons.slice(0, 5), requests: reqs.slice(0, 8) }));
  await b.close();
})();
