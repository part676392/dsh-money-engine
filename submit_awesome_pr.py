import base64, json, subprocess, sys, pathlib

def gh(args, inp=None):
    r = subprocess.run(["gh"] + args, input=inp, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("  gh 失敗: " + " ".join(args[:4]) + " :: " + (r.stderr or r.stdout)[:220])
    return r.stdout

ME = "part676392"
U = "https://part676392.github.io/dsh-money-engine/"

def submit(repo, branch, marker, insert, body, pr_title, spec_edits=None):
    print("=== " + repo)
    owner, name = repo.split("/")
    # 1) fork
    out = gh(["repo", "fork", repo, "--clone=false"])
    print("  fork:", out.strip().splitlines()[-1][:90] if out.strip() else "ok")
    # 2) README を上流から取って差し込む
    # 上流の README は名前が大文字小文字どちらでも来る (実測: contents/README.md は 404)
    meta = json.loads(gh(["api", f"repos/{repo}/readme"]))
    path = meta["path"]
    text = base64.b64decode(meta["content"]).decode("utf-8")
    # edits は複数が普通 (目次に 1 行、本文に 1 節)。1 組なら marker/insert で渡す。
    edits = spec_edits or [(marker, insert)]
    for mk, ins in edits:
        if mk not in text:
            raise SystemExit("  ★ 目印が見つからない: " + mk[:40])
        first = ins.strip().splitlines()[0][:46] if ins.strip() else ""
        if first and first in text:
            print("  ★ 既に入っている行があるので省略: " + first[:36])
            continue
        text = text.replace(mk, ins + mk, 1)
    # 3) branch
    base = gh(["api", f"repos/{repo}", "-q", ".default_branch"]).strip()
    sha = gh(["api", f"repos/{repo}/git/ref/heads/{base}", "-q", ".object.sha"]).strip()
    r = subprocess.run(["gh", "api", "-X", "POST", f"repos/{ME}/{name}/git/refs",
                        "-f", f"ref=refs/heads/{branch}", "-f", f"sha={sha}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # 前の試行で branch が残りていることがある (実測: Reference already exists) -> 今の先を使う
        sha = gh(["api", f"repos/{ME}/{name}/git/ref/heads/{branch}", "-q", ".object.sha"]).strip()
        print(f"  branch {branch} は既存 (先 {sha[:8]}) を使う")
    else:
        print(f"  branch {branch} を {base}@{sha[:8]} から切った")
    # 4) commit
    msg = json.dumps({
        "message": pr_title,
        "content": base64.b64encode(text.encode("utf-8")).decode(),
        "branch": branch,
        "sha": meta["sha"],
    }, ensure_ascii=False)
    res = json.loads(gh(["api", "-X", "PUT", f"repos/{ME}/{name}/contents/{path}", "--input", "-"], inp=msg))
    print("  commit:", res.get("commit", {}).get("sha", "")[:10])
    # 5) PR
    bodyf = pathlib.Path("/tmp/pr_body.md"); bodyf.write_text(body, encoding="utf-8")
    pr = gh(["pr", "create", "--repo", repo, "--head", f"{ME}:{branch}", "--title", pr_title, "--body-file", str(bodyf)])
    print("  PR:", pr.strip())
    return pr.strip()

if __name__ == "__main__":
    which = sys.argv[1]
    spec = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    submit(spec["repo"], spec["branch"], spec["marker"], spec.get("insert", ""), spec["body"], spec["title"], spec.get("edits"))
