"""Upload files queued in uploads/queue.json straight to CurseForge (no Modrinth needed).

Each entry: {"file": "uploads/...", "project": <CurseForge id>, "name": "...", "game": ["1.20.1", ...],
             "loaders": ["fabric", ...] (mods only), "changelog": "...", "requires": ["slug", ...]}
Uploaded files are remembered in uploads/done.json.
"""
import json
import os
import time
import urllib.error

from sync import DRY, FABRIC_API, MOD_LOADERS, cf_versions, upload


def main():
    queue = json.load(open("uploads/queue.json"))
    done_path = "uploads/done.json"
    done = json.load(open(done_path)) if os.path.exists(done_path) else {}
    cfv = cf_versions()
    failures = 0
    for e in queue:
        if e["file"] in done:
            continue
        game = [cfv[("mc", g)] for g in e["game"] if ("mc", g) in cfv]
        loaders = e.get("loaders", [])
        if loaders:
            game += [cfv[("loader", MOD_LOADERS[l])] for l in loaders if ("loader", MOD_LOADERS[l]) in cfv]
            game += [cfv[k] for k in (("env", "Client"), ("env", "Server")) if k in cfv]
        meta = {"changelog": e.get("changelog") or "Update.", "changelogType": "markdown",
                "displayName": e["name"], "gameVersions": game, "releaseType": "release"}
        rel = [{"slug": r, "type": "requiredDependency"} for r in e.get("requires", [])]
        if "fabric" in loaders:
            rel.append({"slug": FABRIC_API, "type": "requiredDependency"})
        if rel:
            meta["relations"] = {"projects": rel}
        print(f"{e['file']} -> CurseForge {e['project']} ({len(game)} versions)")
        if DRY:
            continue
        try:
            fid = upload(e["project"], os.path.basename(e["file"]), open(e["file"], "rb").read(), meta)
            done[e["file"]] = fid
            json.dump(done, open(done_path, "w"), indent=1)
            time.sleep(2)
        except urllib.error.HTTPError as err:
            failures += 1
            print(f"FAILED {e['file']}: {err.code} {err.read().decode()[:300]}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
