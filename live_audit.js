const { chromium } = require("playwright");
(async () => {
  const url = process.argv[2];
  const b = await chromium.launch();
  const p = await (await b.newContext({ locale: "ja-JP" })).newPage();
  const failed = [], badstatus = [];
  p.on("requestfailed", r => failed.push({ url: r.url(), why: (r.failure() || {}).errorText }));
  p.on("response", r => { if (r.status() >= 400) badstatus.push({ url: r.url(), code: r.status() }); });
  try { await p.goto(url, { waitUntil: "networkidle", timeout: 45000 }); }
  catch (e) { console.log("  goto:", e.message.split("\n")[0]); }
  await p.waitForTimeout(2500);
  const imgs = await p.evaluate(() => [...document.images].map(i => ({
    src: i.currentSrc || i.src, ok: i.complete && i.naturalWidth > 0, w: i.naturalWidth })));
  const unresolved = await p.evaluate(() => [...document.querySelectorAll("img")].filter(i => /\$\{/.test(i.getAttribute("src") || "")).length);
  console.log(`  URL ${url}`);
  console.log(`  <img> 実DOM: ${imgs.length} / 読めなかった: ${imgs.filter(i => !i.ok).length} / srcに\${}が残ったまま: ${unresolved}`);
  for (const i of imgs.filter(i => !i.ok).slice(0, 5)) console.log(`    ✗ ${i.src.slice(0, 88)}`);
  console.log(`  network failed: ${failed.length} / HTTP>=400: ${badstatus.length}`);
  for (const f of failed.slice(0, 5)) console.log(`    ✗ ${f.url.slice(0, 80)} (${f.why})`);
  for (const s of badstatus.slice(0, 5)) console.log(`    ✗${s.code} ${s.url.slice(0, 80)}`);
  await b.close();
})();
