// 読者が実際に居る媒体に、機械が垢を作れるか。
// captcha / 電話 / GitHub OAuth の有無を必ず実物DOMで見る。
const { chromium } = require('playwright');
const TARGETS = [
  ['dev.to',  'https://dev.to/enter'],
  ['zenn',    'https://zenn.dev/signup'],
  ['qiita',   'https://qiita.com/signup'],
];
(async () => {
  const b = await chromium.launch();
  for (const [name, u] of TARGETS) {
    const ctx = await b.newContext({ locale: 'en-US' });
    const p = await ctx.newPage();
    try {
      const r = await p.goto(u, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await p.waitForTimeout(4000);
      const s = await p.evaluate(() => ({
        url: location.href,
        inputs: [...document.querySelectorAll('input')].map(i => (i.type || '') + ':' + (i.name || i.id || i.placeholder || '?')).slice(0, 8),
        oauth: [...document.querySelectorAll('button,a')].map(x => (x.innerText || '').trim() + '|' + (x.href || ''))
          .filter(t => /github|google|twitter/i.test(t)).slice(0, 4),
        captcha: /hcaptcha|recaptcha|turnstile|cf-challenge/i.test(document.documentElement.innerHTML),
        text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 170),
      }));
      console.log(`  [${name}] http=${r ? r.status() : '?'} -> ${s.url}`);
      console.log(`     inputs : ${JSON.stringify(s.inputs)}`);
      console.log(`     oauth  : ${JSON.stringify(s.oauth)}`);
      console.log(`     captcha: ${s.captcha}`);
      console.log(`     text   : ${s.text}`);
    } catch (e) { console.log(`  [${name}] ERR ${e.message.split('\n')[0]}`); }
    await ctx.close();
  }
  await b.close();
})();
