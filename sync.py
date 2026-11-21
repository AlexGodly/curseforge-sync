"""Copy every Modrinth version of AlexGodly's projects to the matching CurseForge project.

Data pack versions go to the CurseForge data pack project, mod jars to the mod project.
Uploaded Modrinth version ids are remembered in synced.json so nothing is sent twice.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

MR = "https://api.modrinth.com/v2"
CF = "https://minecraft.curseforge.com/api"
UA = {"User-Agent": "AlexGodly/curseforge-sync"}
TOKEN = os.environ.get("CURSEFORGE_TOKEN", "")
DRY = os.environ.get("DRY_RUN") == "1"
MOD_LOADERS = {"fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt"}
FABRIC_API = "fabric-api"


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def download(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return r.read()


def cf_versions():
    types = {t["id"]: t["slug"] for t in get(f"{CF}/game/version-types", {"X-Api-Token": TOKEN})}
    by_name = {}
    for v in get(f"{CF}/game/versions", {"X-Api-Token": TOKEN}):
        slug = types.get(v["gameVersionTypeID"], "")
        if slug.startswith("minecraft-"):
            by_name.setdefault(("mc", v["name"]), v["id"])
        elif slug == "modloader":
            by_name.setdefault(("loader", v["name"]), v["id"])
    return by_name


def upload(project_id, filename, data, metadata):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{CF}/projects/{project_id}/upload-file", data=body, method="POST",
                                 headers={**UA, "X-Api-Token": TOKEN,
                                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["id"]


def main():
    projects = json.load(open("projects.json"))
    synced = json.load(open("synced.json")) if os.path.exists("synced.json") else {}
    cfv = cf_versions()
    only = set(sys.argv[1:])
    failures = 0

    for slug, targets in projects.items():
        if only and slug not in only:
            continue
        try:
            versions = get(f"{MR}/project/{slug}/version")
        except urllib.error.HTTPError as e:
            print(f"[{slug}] not readable on Modrinth yet ({e.code}), skipping")
            continue
        for v in sorted(versions, key=lambda v: v["date_published"]):
            loaders = [l for l in v["loaders"] if l in MOD_LOADERS]
            kind = "mod" if loaders else "datapack"
            cf_id = targets.get(kind)
            if not cf_id:
                continue
            key = str(cf_id)
            if v["id"] in synced.get(key, []):
                continue
            game = [cfv[("mc", g)] for g in v["game_versions"] if ("mc", g) in cfv]
            if not game:
                print(f"[{slug}] {v['version_number']}: no CurseForge game versions for {v['game_versions']}, skipping")
                continue
            if kind == "mod":
                game += [cfv[("loader", MOD_LOADERS[l])] for l in loaders if ("loader", MOD_LOADERS[l]) in cfv]
            primary = next((f for f in v["files"] if f["primary"]), v["files"][0])
            meta = {
                "changelog": v.get("changelog") or "Update.",
                "changelogType": "markdown",
                "displayName": v["name"] or primary["filename"],
                "gameVersions": game,
                "releaseType": {"release": "release", "beta": "beta", "alpha": "alpha"}.get(v["version_type"], "release"),
            }
            if kind == "mod" and "fabric" in loaders:
                meta["relations"] = {"projects": [{"slug": FABRIC_API, "type": "requiredDependency"}]}
            print(f"[{slug}] {v['version_number']} -> CurseForge {cf_id} ({kind}, {len(game)} versions)")
            if DRY:
                continue
            try:
                file_id = upload(cf_id, primary["filename"], download(primary["url"]), meta)
                for extra in v["files"]:
                    if extra is primary or extra.get("file_type") != "required-resource-pack":
                        continue
                    upload(cf_id, extra["filename"], download(extra["url"]),
                           {"changelog": "Resource pack with the sounds.", "changelogType": "markdown",
                            "parentFileID": file_id, "releaseType": meta["releaseType"]})
                synced.setdefault(key, []).append(v["id"])
                json.dump(synced, open("synced.json", "w"), indent=1)
                time.sleep(2)
            except urllib.error.HTTPError as e:
                failures += 1
                print(f"   FAILED {e.code}: {e.read().decode()[:300]}")

    json.dump(synced, open("synced.json", "w"), indent=1)
    if failures:
        sys.exit(f"{failures} uploads failed")


if __name__ == "__main__":
    main()
