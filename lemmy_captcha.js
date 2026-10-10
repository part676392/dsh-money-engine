const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
(async () => {
  const inst = process.argv[2] || "lemmy.world";
  const ctx = await chromium.launchPersistentContext(path.join(__dirname, ".lemmy-" + inst), {
    headless: true, locale: "en-US", viewport: { width: 1280, height: 900 },
  });
  const p = await ctx.newPage();
  await p.goto("https://" + inst + "/", { waitUntil: "domcontentloaded", timeout: 60000 })
        .catch(e => console.log("  home:", e.message.split("\n")[0]));
  const url = "https://" + inst + "/api/v3/user/captcha?rng=" + Math.random();
  const r = await p.evaluate(async (u) => {
    const res = await fetch(u, { credentials: "include" });
    const ct = res.headers.get("content-type");
    let j = null;
    try { j = await res.json(); } catch (e) { j = { parse_error: String(e).slice(0, 70) }; }
    return { status: res.status, ct: ct, keys: j ? Object.keys(j) : [],
             uuid: j && j.uuid, inner_ct: j && j.content_type,
             payload_len: j && ((j.png || j.svg || "").length) };
  }, url);
  console.log("  probe " + inst + ":", JSON.stringify(r));
  if (r.uuid) {
    const full = await p.evaluate(async (u) => (await fetch(u, { credentials: "include" })).json(), url);
    fs.writeFileSync("/tmp/cap-" + inst + ".json", JSON.stringify(full));
    const raw = Buffer.from(full.png || full.svg || "", "base64").toString("utf8");
    console.log("  inner content_type:", full.content_type);
    if (String(full.content_type).includes("svg")) {
      const texts = [...raw.matchAll(/>([^<>]{1,24})</g)].map(m => m[1]).filter(Boolean);
      console.log("  SVG text nodes:", JSON.stringify(texts.slice(0, 14)));
      const js = raw.match(/<text[^>]*>([^<]+)<\/text>/g) || [];
      console.log("  <text> elements:", js.length, JSON.stringify(js.slice(0, 3)).slice(0, 200));
    } else {
      console.log("  not svg; first bytes:", raw.slice(0, 16));
    }
  }
  await ctx.close();
})();
