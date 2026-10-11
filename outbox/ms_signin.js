const { chromium } = require('playwright');
const fs = require('fs');
const cred = JSON.parse(fs.readFileSync('outbox/mailtm.json','utf8'));
const acct = JSON.parse(fs.readFileSync('outbox/ms-account.json','utf8'));
const log = s => console.error(s);
(async () => {
  const ctx = await chromium.launchPersistentContext('.ext-profile', { locale:'en-US', viewport:{width:1280,height:900} });
  const p = await ctx.newPage();
  const text = () => p.evaluate(() => (document.body.innerText||'').replace(/\s+/g,' ').slice(0,240));
  try {
    await p.goto('https://login.live.com/', { waitUntil:'domcontentloaded', timeout:60000 });
    await p.waitForTimeout(4500);
    for (let i = 0; i < 8; i++) {
      const t = await text();
      log('  [' + i + '] ' + p.url().slice(0,70) + ' | ' + t.slice(0,100));
      if (/Enter your email|Sign in/.test(t)) {
        const e = p.locator('input[type="email"], input[name="loginfmt"], #i0116').first();
        if (await e.count()) { await e.click(); await e.fill(cred.address); await p.waitForTimeout(1000);
          await p.locator('#idSIButton9, button:has-text("Next"), input[value="Next"]').first().click().catch(()=>{});
          await p.waitForTimeout(6500); continue; }
      }
      if (/Enter password|Password/i.test(t)) {
        const w = p.locator('#i0118, input[type="password"], #Password').first();
        if (await w.count()) { await w.fill(acct.password); await p.waitForTimeout(900);
          await p.locator('#idSIButton9, input[type=submit]').first().click().catch(()=>{});
          await p.waitForTimeout(7000); continue; }
      }
      if (/Stay signed in|Keep me signed in/i.test(t)) {
        await p.locator('#idBtn_Back, button:has-text("No")').first().click().catch(()=>{});
        await p.waitForTimeout(5000); continue;
      }
      if (/Add some details|birthdate/i.test(t)) {
        const info = await p.evaluate(() => [...document.querySelectorAll('input,select,[role=combobox],[aria-label]')]
          .filter(e => e.offsetParent).map(e => ({tag: e.tagName, id: e.id, aria: e.getAttribute('aria-label')})).slice(0, 12));
        log('      詳細欄: ' + JSON.stringify(info).slice(0, 420));
        break;
      }
      if (/error|doesn.t exist|wrong/i.test(t)) { log('  ★ エラー語: ' + t.slice(0,140)); break; }
      break;
    }
    log('  → Bing WMT へ');
    await p.goto('https://www.bing.com/webmasters/home', { waitUntil:'domcontentloaded', timeout:70000 });
    await p.waitForTimeout(8000);
    const t = await text();
    log('  [wmt] ' + p.url().slice(0,90));
    log('        ' + t.slice(0,220));
    fs.writeFileSync('outbox/ms-signin-result.json', JSON.stringify({url: p.url(), text: t}, null, 1));
  } catch (e) { log('ERR ' + String(e).slice(0,180)); }
  await ctx.close();
})();
