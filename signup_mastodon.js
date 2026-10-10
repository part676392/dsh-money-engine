// Mastodon の登録を実ブラウザで通す.
//
//   sign_up 頁は React の客户端描画で、curl では input が 1 本 (authenticity_token) しか
//   見えない。実際は二段構え: まず rules の Accept、その後 Username/Email/Password。
//   前回の自分の失敗: ステップラの "Confirm email" という**ラベル**を
//   「確認メールを送った」と誤読した。だからここは (a) 詳細を入力した後の応答だけを
//   確認扱いにする、(b) 画面の文面をそのまま出す、の二つを守る。
const { chromium } = require("playwright");
const fs = require("fs");

const cred = JSON.parse(fs.readFileSync("outbox/mailtm-mastodon.json", "utf8"));
const HOST = process.argv[2] || "mastodon.social";
const USER = process.env.MU || ("dsh_lab_" + Math.random().toString(36).slice(2, 8));
const PW = cred.password;

// 「確認メールを送った」系の文面。ステップラのラベルとは別物に限定する。
const CONFIRM = /(instruction.*e-?mailed|a message was sent|we sent (you|an)|click the link in (the |your )?(e-?mail)|confirm( your)? e-?mail address|please check (your )?(e-?mail|inbox))/i;
const PROBLEM = /(is not available|already taken|not allowed|blocked|invalid|couldn|error occurred|please choose|must be at least)/i;

(async () => {
  const b = await chromium.launch({ headless: true });
  const ctx = await b.newContext({
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    locale: "en-US", viewport: { width: 1280, height: 900 } });
  const pg = await ctx.newPage();
  const netfail = [];
  pg.on("requestfailed", r => netfail.push(r.url().slice(0, 70)));

  await pg.goto(`https://${HOST}/auth/sign_up`, { waitUntil: "domcontentloaded", timeout: 45000 });
  await pg.waitForTimeout(2500);

  let filledAt = 0, outcome = { reached: false }, round = 0;
  while (round < 5) {
    round++;
    const inputs = await pg.$$eval("input", els => els.map(e => ({ id: e.id || "", name: e.name || "", type: e.type || "" })));
    // mastodon.social の実測: 詳細フォームの名前は user_account_attributes_username で、
    // しかも date_of_birth の select を要求する。#user_username は別のインスタンス用。
    const hasUser = inputs.some(f => /username/i.test(f.id + f.name));
    const captcha = await pg.evaluate(() => !!document.querySelector(
      "[class*=captcha],[id*=captcha],iframe[src*=captcha],.cf-turnstile"));
    console.log(JSON.stringify({ round, inputs: inputs.length, hasUser, captcha,
      ids: inputs.map(f => f.id || f.name).slice(0, 9) }));
    if (captcha) { outcome = { reached: false, blocked: "captcha appeared" }; break; }

    if (hasUser) {
      const put = async (sel, val) => {
        const el = await pg.$(sel);
        if (!el) return false;
        await el.click().catch(() => {});
        await el.fill(val).catch(() => {});
        return true;
      };
      // 名前パターンで全部埋める (インスタンスごとに field が違うので列挙しない)。
      const spec = await pg.$$eval("input, select", els => els.map(e => ({
        tag: e.tagName, id: e.id || "", name: e.name || "", type: e.type || "",
        opts: e.tagName === "SELECT" ? Array.from(e.options).slice(0, 3).map(o => o.value) : [] })));
      const done = {};
      for (const f of spec) {
        const key = (f.id || f.name || "").toLowerCase();
        if (!key) continue;
        const sel = `#${f.id || ""}`.replace(/^#$/, `[name="${f.name}"]`);
        if (f.tag === "SELECT") {
          let v = null;
          if (/birth_1i|year/.test(key)) v = "1990";
          else if (/birth_2i|month/.test(key)) v = "6";
          else if (/birth_3i|day/.test(key)) v = "15";
          if (v === null) continue;
          if (!f.opts.length) continue;
          const num = /^\d+$/.test(v) ? String(parseInt(v, 10)) : v;
          const pick = f.opts.includes(v) ? v : (f.opts.includes(num) ? num : f.opts[0]);
          await pg.selectOption(sel, pick).catch(() => {});
          done[key] = pick;
          continue;
        }
        // 生年月日は select ではなく **input type=text** (mastodon.social 実測)。
        // selectOption を撃っていたのが空振りの原因で、required が空のまま
        // submit がサイレントに止まっていた。
        if (/date_of_birth_1i|birth.*year/.test(key)) { done[key] = await put(sel, "1990"); }
        else if (/date_of_birth_2i|birth.*month/.test(key)) { done[key] = await put(sel, "06"); }
        else if (/date_of_birth_3i|birth.*day/.test(key)) { done[key] = await put(sel, "15"); }
        else if (/username/.test(key)) { done[key] = await put(sel, USER); }
        else if (/email/.test(key)) { done[key] = await put(sel, cred.address); }
        else if (/password/.test(key)) { done[key] = await put(sel, PW); }
        else if (/website|website|url/.test(key)) { done[key] = await put(sel, "https://part676392.github.io/dsh-money-engine"); }
      }
      console.log(JSON.stringify({ round, action: "fill", filled: done, username: USER }));
      const cb = await pg.$("#tos-checkbox, input[type=checkbox]");
      if (cb) { await cb.check({ force: true }).catch(() => {}); console.log(JSON.stringify({ round, action: "tos" })); }
      filledAt = round;
    }

    const btn = await pg.$('button[type=submit], input[type=submit], button:has-text("Create account"), button:has-text("Continue"), button:has-text("Accept")');
    if (!btn) { outcome = { reached: false, blocked: "no submit button", round }; break; }
    const label = (await btn.innerText().catch(() => "")).trim().slice(0, 28);
    await btn.click().catch(() => {});
    await pg.waitForTimeout(6000);
    const body = (await pg.evaluate(() => document.body.innerText) || "").replace(/\s+/g, " ");
    const errs = await pg.$$eval('[class*=error], .error, [role=alert], .warning',
      els => els.map(e => e.innerText.trim()).filter(Boolean).slice(0, 5)).catch(() => []);
    console.log(JSON.stringify({ round, action: "submit", button: label, url: pg.url(),
      errs, confirm: CONFIRM.test(body), problem: PROBLEM.test(body) }));

    if (errs.length) outcome.errs = errs;
    if (filledAt && round >= filledAt && CONFIRM.test(body)) {
      outcome = { reached: true, round, url: pg.url(), body_start: body.slice(0, 320) };
      break;
    }
    if (PROBLEM.test(body)) { outcome = { reached: false, round, problem: body.slice(0, 300) }; break; }
  }

  const finalBody = (await pg.evaluate(() => document.body.innerText) || "").replace(/\s+/g, " ");
  const rec = { host: HOST, username: USER, email: cred.address, at: new Date().toISOString(),
    url: pg.url(), netfail: netfail.length, ...outcome, tail: finalBody.slice(0, 200) };
  fs.writeFileSync("outbox/mastodon-signup.json", JSON.stringify(rec, null, 1));
  console.log(JSON.stringify({ FINAL: rec.reached === true, blocked: rec.blocked || null,
    errs: rec.errs || [], username: USER, url: rec.url }, null, 1));
  await b.close();
})();
