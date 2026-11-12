import argparse
import json
import os
import re
import urllib.request
from pathlib import Path


def get_json(url, *, api=False):
    headers = {"User-Agent": "DalamudPlugins"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
        token = os.getenv("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def find_release(source, fetch):
    repo = source["repository"]
    prefix = source["tagPrefix"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"Invalid repository: {repo}")
    pattern = re.compile(re.escape(prefix) + r"([0-9]+(?:\.[0-9]+){3})")
    candidates = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        releases = fetch(url, api=True)
        for release in releases:
            match = pattern.fullmatch(release["tag_name"])
            if match and not release["draft"] and not release["prerelease"]:
                version = match[1]
                candidates.append((tuple(map(int, version.split("."))), version, release))
        if len(releases) < 100:
            break
        page += 1
    if not candidates:
        return None
    _, version, release = max(candidates, key=lambda candidate: candidate[0])
    return version, release


def make_entry(source, fetch):
    name = source["internalName"]
    result = find_release(source, fetch)
    if result is None:
        return None
    version, release = result
    assets = {asset["name"]: asset for asset in release["assets"] if asset["state"] == "uploaded"}
    for filename in (f"{name}.json", "latest.zip"):
        if filename not in assets or assets[filename]["size"] <= 0:
            raise ValueError(f"{release['tag_name']} is missing {filename}")
    manifest = fetch(assets[f"{name}.json"]["browser_download_url"])
    if manifest["InternalName"] != name or manifest["AssemblyVersion"] != version:
        raise ValueError(f"The manifest does not match {name} {release['tag_name']}")
    if not manifest["Name"].strip() or not isinstance(manifest["DalamudApiLevel"], int) or manifest["DalamudApiLevel"] < 1:
        raise ValueError(f"Invalid plugin name or API level in {name} {release['tag_name']}")
    download = assets["latest.zip"]["browser_download_url"]
    manifest["DownloadLinkInstall"] = download
    manifest["DownloadLinkUpdate"] = download
    return manifest


def generate(sources, fetch=get_json):
    entries = [entry for entry in (make_entry(source, fetch) for source in sources) if entry is not None]
    names = {entry["InternalName"].casefold() for entry in entries}
    if len(names) != len(entries):
        raise ValueError("Plugin internal names must be unique")
    return sorted(entries, key=lambda entry: entry["InternalName"].casefold())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("pluginmaster.json"))
    args = parser.parse_args()
    entries = generate(json.loads(args.sources.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
