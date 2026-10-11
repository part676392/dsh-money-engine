// Microsoft account を agent のメールで作り切る (人間の指紋を借りないための driving)。
// 実測で分かった型: #nextButton は無い (Next は id 空の button)。email の fill が途中で切れるので打鍵で入れる。
const { chromium } = require('playwright');
const fs = require('fs');
const cred = JSON.parse(fs.readFileSync('outbox/mailtm.json', 'utf8'));
const acct = JSON.parse(fs.readFileSync('outbox/ms-account.json', 'utf8'));
const log = s => console.error(s);
async function mailToken() {
  const r = await fetch('https://api.mail.tm/token', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address: cred.address, password: cred.password }) });
  if (!r.ok) throw new Error('mail.tm login ' + r.status);
  return (await r.json()).token;
}
async function waitCode(tok, after) {
  for (let i = 0; i < 16; i++) {
    const d = await (await fetch('https://api.mail.tm/messages?page=1', { headers: { Authorization: 'Bearer ' + tok } })).json();
    for (const m of (d['hydra:member'] || [])) {
      if (new Date(m.createdAt).getTime() < after - 5000) continue;
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
(async () => {
  const tok = await mailToken();
  const t0 = Date.now();
  const ctx = await chromium.launchPersistentContext('.ext-profile', { locale: 'en-US', viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage();
  const text = () => p.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 260));
  const next = async () => {
    const b = p.locator('button:has-text("Next"), input[value="Next"], #idSIButton9').first();
    if (await b.count()) { await b.click().catch(e => log('  next click 失敗 ' + String(e).slice(0, 70))); await p.waitForTimeout(7000); return true; }
    return false;
  };
  try {
    await p.goto('https://signup.live.com/signup?lic=1&mkt=en-US', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await p.waitForTimeout(4000);
    for (let round = 0; round < 12; round++) {
      const t = await text();
      log('  [' + round + '] ' + p.url().slice(0, 66) + ' | ' + t.slice(0, 88));
      if (/Enter your email address/i.test(t)) {
        const e = p.locator('input[type="email"]').first();
        if (await e.count()) { await e.click(); await p.waitForTimeout(300);
          await e.pressSequentially(cred.address, { delay: 45 }); await p.waitForTimeout(900);
          const val = await e.inputValue(); log('      email 入力の実際: ' + val);
          await p.keyboard.press('Tab'); await p.waitForTimeout(600); await next(); continue; }
      }
      if (/Verify your email/i.test(t)) {
        const code = await waitCode(tok, t0);
        if (!code) { log('  ★ code が取れない'); break; }
        for (let j = 0; j < 6; j++) { const b = p.locator('#codeEntry-' + j); if (await b.count()) await b.fill(code[j]).catch(() => {}); }
        await p.waitForTimeout(1200); await next(); continue;
      }
      if (/password/i.test(t)) {
        const w = p.locator('input[type="password"], #Password').first();
        if (await w.count()) { await w.click(); await w.pressSequentially(acct.password, { delay: 25 });
          await p.waitForTimeout(800); await p.keyboard.press('Tab'); await p.waitForTimeout(400); await next(); continue; }
      }
      if (/Add some details/i.test(t)) {
        const info = await p.evaluate(() => ({
          inputs: [...document.querySelectorAll('input')].filter(e => e.offsetParent).map(e => ({ id: e.id, type: e.type, aria: e.getAttribute('aria-label'), ph: e.placeholder })),
          combos: [...document.querySelectorAll('[role=combobox],select')].filter(e => e.offsetParent).map(e => ({ id: e.id, aria: e.getAttribute('aria-label'), tag: e.tagName })),
          btns: [...document.querySelectorAll('button')].filter(e => e.offsetParent).map(e => (e.innerText || '').trim().slice(0, 18))}));
        log('      詳細欄: ' + JSON.stringify(info).slice(0, 620));
        break;
      }
      if (/already (has|have)|an account with this email/i.test(t)) { log('  ★ 既存扱い: ' + t.slice(0, 120)); break; }
      if (!/signup\.live/i.test(p.url())) { log('  signup を出た: ' + p.url().slice(0, 90)); break; }
      await p.waitForTimeout(3000);
    }
    fs.writeFileSync('outbox/ms-auto-result.json', JSON.stringify({ url: p.url(), text: await text().catch(() => '') }, null, 1));
  } catch (e) { log('ERR ' + String(e).slice(0, 180)); }
  await ctx.close();
})();
