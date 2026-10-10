import re,sys,urllib.request,urllib.error,concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
def get(u,t=18):
    return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t)
def probe(u):
    d={"url":u}
    try:
        with get(u) as r:
            d["http"]=r.status; h=r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        d["http"]=e.code; return d
    except Exception as e:
        d["http"]="ERR"; d["err"]=str(e)[:40]; return d
    low=h.lower()
    d["jp"]=bool(re.search(r"[ぁ-んァ-ン]",h))
    d["no_viewport"]="viewport" not in low
    d["no_lang"]='html lang=' not in low.replace('"',"'") and "html lang" not in low
    d["no_desc"]='name="description"' not in low and "name='description'" not in low
    d["no_og"]=not any(k in low for k in ('og:image','og:title'))
    d["no_alt"]= 'alt=""' in low or "<img" in low and "alt=" not in low
    # asset 404 検査
    assets=set(re.findall(r'(?:src|href)=["\']([^"\']+\.(?:css|js|png|jpe?g|webp|svg))["\']',h,re.I))
    base=u if u.endswith("/") else u.rsplit("/",1)[0]+"/"
    broken=[]; checked=0
    for a in list(assets)[:6]:
        au=a if a.startswith("http") else (urllib.parse.urljoin(u,a) if a.startswith("/") else base+a)
        checked+=1
        try:
            with get(au,12) as r:
                if r.status>=400: broken.append((r.status,au[:70]))
        except urllib.error.HTTPError as e: broken.append((e.code,au[:70]))
        except Exception: broken.append(("ERR",au[:70]))
    d["assets_checked"]=checked; d["broken_assets"]=broken[:4]
    d["score"]=sum([d["no_viewport"],d["no_desc"],d["no_og"],bool(broken),d["no_lang"]])
    return d
import urllib.parse
urls=[l.strip() for l in open("/tmp/prospects.txt") if l.strip()]
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    res=list(ex.map(probe,urls))
res=[r for r in res if r.get("http")==200]
res.sort(key=lambda r:(-r["score"], not r.get("jp")))
print(f"\n  検査成功 {len(res)} サイト / 日本語サイト {sum(1 for r in res if r.get('jp'))}")
print("\n  スコア順（欠陥いくつ: viewport/desc/og/broken-asset/lang）")
for r in res[:12]:
    fl=[k for k in ("no_viewport","no_desc","no_og","no_lang") if r.get(k)]
    print(f"   score={r['score']} jp={'✓' if r.get('jp') else '-'} {r['url'][:56]}")
    print(f"        {','.join(x.replace('no_','') for x in fl)}{' +broken:'+str(len(r['broken_assets'])) if r['broken_assets'] else ''}")
    for c,a in r["broken_assets"][:2]: print(f"        ✗{c} {a}")
import json; json.dump(res,open("data/prospect_scan.json","w"),ensure_ascii=False,indent=1)
print("\n  saved data/prospect_scan.json")
