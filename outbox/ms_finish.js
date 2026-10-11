// details (生年月日) まで進めたので、そこを閉める。combobox は BUTTON + listbox の型 (実測)。
const { chromium } = require('playwright');
const fs = require('fs');
const cred = JSON.parse(fs.readFileSync('outbox/mailtm.json', 'utf8'));
const acct = JSON.parse(fs.readFileSync('outbox/ms-account.json', 'utf8'));
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const log = s => console.error(s);
async function mailToken() {
  const r = await fetch('https://api.mail.tm/token', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address: cred.address, password: cred.password }) });
  return (await r.json()).token;
}
async function waitCode(tok, after) {
  for (let i = 0; i < 26; i++) {
    const d = await (await fetch('https://api.mail.tm/messages?page=1', { headers: { Authorization: 'Bearer ' + tok } })).json();
    for (const m of (d['hydra:member'] || [])) {
      if (new Date(m.createdAt).getTime() < after) continue;
      if (!/microsoft/i.test((m.from && m.from.address) || '')) continue;
      const f = await (await fetch('https://api.mail.tm/messages/' + m.id, { headers: { Authorization: 'Bearer ' + tok } })).json();
      const txt = f.text || String(Array.isArray(f.html) ? f.html.join(' ') : f.html || '').replace(/<[^>]+>/g, ' ');
      const mm = txt.match(/\b(\d{4})-?(\d{2})\b/);
      if (mm) { log('  code 受信: ' + mm[1] + mm[2]); return mm[1] + mm[2]; }
    }
    await new Promise(r => setTimeout(r, 5000));
  }
  return '';
}
async function pick(p, btnSel, optText) {
  const b = p.locator(btnSel).first();
  if (!(await b.count())) { log('  ★ ' + btnSel + ' が無い'); return false; }
  await b.scrollIntoViewIfNeeded().catch(() => {});
  try { await b.click({ timeout: 8000 }); }
  catch (e) {
    log('      click 失敗 (' + String(e).slice(0, 50) + ') -> evaluate で押す');
    const cov = await p.evaluate(() => { const x = document.elementFromPoint(640, 420);
      return x ? (x.tagName + '#' + (x.id || '') + ' ' + (x.className || '').toString().slice(0, 60)) : 'none'; });
    log('      中央を塞いでいる物: ' + cov);
    await b.evaluate(el => el.click()).catch(() => {});
  }
  await p.waitForTimeout(1400);
  const opt = p.locator('[role=option]:visible', { hasText: optText }).first();
  if (await opt.count()) { await opt.click(); await p.waitForTimeout(900); log('      選んだ: ' + btnSel + ' = ' + optText); return true; }
  const alt = p.locator('li:visible, [role=listbox] >> text=' + optText).first();
  if (await alt.count()) { await alt.click(); await p.waitForTimeout(900); log('      選んだ (li): ' + optText); return true; }
  log('  ★ 選択肢が見つからない: ' + optText); return false;
}
(async () => {
  const tok = await mailToken();
  const t0 = Date.now();
  const ctx = await chromium.launchPersistentContext('.ext-profile', { locale: 'en-US', viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage();
  const text = () => p.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300));
  const next = async () => { const b = p.locator('button:has-text("Next"), #idSIButton9').first();
    if (await b.count()) { await b.click().catch(() => {}); await p.waitForTimeout(7000); return true; } return false; };
  try {
    await p.goto('https://signup.live.com/signup?lic=1&mkt=en-US', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await p.waitForTimeout(4000);
    const [BY, BM, BD] = acct.birth.split('-');
    for (let round = 0; round < 12; round++) {
      const t = await text();
      log('  [' + round + '] ' + t.slice(0, 80));
      if (/Enter your email address/i.test(t)) {
        const e = p.locator('input[type="email"]').first();
        if (await e.count()) { await e.click(); await e.fill(''); await p.waitForTimeout(200);
          await e.pressSequentially(cred.address, { delay: 40 });
          await p.waitForTimeout(800); await p.keyboard.press('Tab'); await next(); continue; }
      }
      if (/Verify your email/i.test(t)) {
        let code = await waitCode(tok, Date.now() - 20 * 60 * 1000);
        if (!code) { const rs = p.locator('text=/Resend code/i').first();
          if (await rs.count()) { await rs.click().catch(() => {}); log('      Resend を押した'); }
          code = await waitCode(tok, Date.now() - 60 * 1000);
          if (!code) { log('  ★ code が取れない'); break; } }
        log('      code を入れる: ' + code);
        for (let j = 0; j < 6; j++) { const b = p.locator('#codeEntry-' + j); if (await b.count()) await b.fill(code[j]).catch(() => {}); }
        await p.waitForTimeout(1200); await next();
        const after = await text();
        if (/Verify your email/i.test(after)) { log('  ★ code が通らなかったのでもう一度送らせる');
          const rs = p.locator('text=/Resend code/i').first(); if (await rs.count()) { await rs.click().catch(() => {}); }
          const c2 = await waitCode(tok, Date.now() - 90 * 1000);
          if (!c2) break;
          log('      2 回目の code: ' + c2);
          for (let j = 0; j < 6; j++) { const b = p.locator('#codeEntry-' + j); if (await b.count()) await b.fill(c2[j]).catch(() => {}); }
          await p.waitForTimeout(1200); await next(); }
        continue;
      }
      if (/password/i.test(t)) {
        const w = p.locator('input[type="password"], #Password').first();
        if (await w.count()) { await w.click(); await w.pressSequentially(acct.password, { delay: 25 });
          await p.waitForTimeout(700); await p.keyboard.press('Tab'); await p.waitForTimeout(400); await next(); continue; }
      }
      if (/too many|try again later|後で/i.test(t)) {
        log('  ★ Microsoft が code 発行を限速した: ' + t.slice(0, 130));
        fs.writeFileSync('outbox/ms-auto-result.json', JSON.stringify({ url: p.url(), text: t, blocked: 'rate_limit' }, null, 1));
        fs.writeFileSync('outbox/ms-state.json', JSON.stringify({
          attempted_on: new Date().toISOString().slice(0, 10), completed: false,
          blocked: 'rate_limit', at: new Date().toISOString(), url: p.url() }, null, 1));
        break;
      }
      if (/Add some details/i.test(t)) {
        await pick(p, '#BirthMonthDropdown', MONTHS[Number(BM) - 1]);
        await pick(p, '#BirthDayDropdown', String(Number(BD)));
        const y = p.locator('input[aria-label="Birth year"], input[type=number]').first();
        if (await y.count()) { await y.click(); await y.fill(BY); await p.waitForTimeout(500); log('      year 入力: ' + BY); }
        await p.keyboard.press('Tab'); await p.waitForTimeout(600);
        await next(); continue;
      }
      if (/Stay signed in|Keep me signed in/i.test(t)) {
        const no = p.locator('button:has-text("No"), #idBtn_Back').first();
        if (await no.count()) { await no.click().catch(() => {}); await p.waitForTimeout(5000); continue; }
      }
      if (!/signup\.live/i.test(p.url())) { log('  ★ signup を出た: ' + p.url().slice(0, 90)); break; }
      await p.waitForTimeout(3000);
    }
    const fin = await text();
    log('  最終 URL: ' + p.url().slice(0, 96));
    log('  最終 text: ' + fin.slice(0, 200));
    const done = !/signup\.live/i.test(p.url());
    const blocked = /too many|try again later/i.test(fin) ? 'rate_limit' : '';
    fs.writeFileSync('outbox/ms-auto-result.json', JSON.stringify({ url: p.url(), text: fin }, null, 1));
    fs.writeFileSync('outbox/ms-state.json', JSON.stringify({
      attempted_on: new Date().toISOString().slice(0, 10),
      completed: done, blocked, at: new Date().toISOString(), url: p.url() }, null, 1));
    await p.goto('https://www.bing.com/webmasters/home', { waitUntil: 'domcontentloaded', timeout: 70000 });
    await p.waitForTimeout(9000);
    const w = await text();
    log('  [WMT] ' + p.url().slice(0, 96));
    log('        ' + w.slice(0, 240));
    fs.writeFileSync('outbox/wmt-state.json', JSON.stringify({ url: p.url(), text: w }, null, 1));
  } catch (e) { log('ERR ' + String(e).slice(0, 200)); }
  await ctx.close();
})();
