// dev.to の signup form の実物構造を見る。当てずっぽうで埋めない。
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('https://dev.to/enter', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForTimeout(3500);
  const f = await p.evaluate(() => {
    const forms = [...document.querySelectorAll('form')].map(fm => ({
      action: fm.getAttribute('action'), method: fm.method,
      fields: [...fm.querySelectorAll('input,select')].map(i => i.type + ':' + (i.name || '?')).slice(0, 10),
      btn: [...fm.querySelectorAll('button,input[type=submit]')].map(x => (x.innerText || x.value || '').trim()).slice(0, 2),
    }));
    return { forms: forms.slice(0, 8), text: (document.body.innerText || '').replace(/\n+/g, ' | ').slice(0, 300) };
  });
  console.log(JSON.stringify(f, null, 1).slice(0, 2400));
  await b.close();
})();
