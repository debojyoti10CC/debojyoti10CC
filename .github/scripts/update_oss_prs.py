"""Rebuild the "Open Source Contributions" table in README.md.

Lists pull requests opened by GITHUB_USER in repositories owned by someone
else with at least MIN_STARS stars (skipping names matching SKIP_REPO_REGEX), using GitHub's search API. Merged PRs come first, then open ones; PRs
that were closed without merging are left out. The table is written between
the OSS-PRS markers in README.md, and the file is only rewritten if it changed.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

USER = os.environ.get("GITHUB_USER", "debojyoti10CC")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.environ.get("README_PATH", "README.md")
# Only list repositories with at least this many stars, to keep out practice
# and personal repos.
MIN_STARS = int(os.environ.get("MIN_STARS", "20"))
# Repository names matching this are skipped (e.g. Hacktoberfest practice repos).
# PRs to leave out of the table even though they are open.
EXCLUDE_URLS = {
    "https://github.com/keep-starknet-strange/awesome-starkzap/pull/38",
}
# PRs closed without a merge whose change still landed (e.g. cherry-picked, or folded into
# another PR). Format: "owner/repo#123=note,owner/repo#456=note".
LANDED = dict(
    item.split("=", 1)
    for item in os.environ.get("LANDED_PRS", "").split(",")
    if "=" in item
)
SKIP_REPO = re.compile(os.environ.get("SKIP_REPO_REGEX", r"hacktober|hactober|pull-a-thon"), re.I)
START, END = "<!-- OSS-PRS:START -->", "<!-- OSS-PRS:END -->"


def api(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


_stars: dict[str, int] = {}


def stars(repo: str) -> int:
    if repo not in _stars:
        try:
            _stars[repo] = api(f"https://api.github.com/repos/{repo}").get("stargazers_count", 0)
        except urllib.error.HTTPError:
            _stars[repo] = 0
    return _stars[repo]


def search(query: str) -> list[dict]:
    items, page = [], 1
    while True:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
            {"q": query, "sort": "created", "order": "desc", "per_page": 100, "page": page}
        )
        data = api(url)
        items += data["items"]
        if len(items) >= data["total_count"] or not data["items"] or page >= 10:
            return items
        page += 1


def cell(text: str) -> str:
    return html.escape(text, quote=False).replace("|", r"\|")


def build_table() -> str:
    prs = search(f"is:pr author:{USER} -user:{USER}")
    rows = []
    for pr in prs:
        repo = pr["repository_url"].split("/repos/", 1)[1]
        merged = bool(pr.get("pull_request", {}).get("merged_at"))
        landed = LANDED.get(f"{repo}#{pr['number']}")
        if pr["state"] == "closed" and not merged and not landed:
            continue
        if SKIP_REPO.search(repo) or stars(repo) < MIN_STARS:
            continue
        if pr["html_url"] in EXCLUDE_URLS:
            continue
        if merged:
            status, order = "✅ Merged", 0
        elif landed:
            status, order = f"✅ Landed ({landed})", 0
        elif pr.get("draft"):
            status, order = "📝 Draft", 2
        else:
            status, order = "🟡 Open", 1
        rows.append((order, pr["created_at"], repo, pr["title"], pr["html_url"], status))
    # Merged first, then open, then drafts; newest first within each group.
    rows.sort(key=lambda r: r[1], reverse=True)
    rows.sort(key=lambda r: r[0])
    lines = ["| Repository | Pull Request | Status |", "| :--- | :--- | :--- |"]
    for _, _, repo, title, url, status in rows:
        lines.append(f"| **{repo}** | [{cell(title)}]({url}) | {status} |")
    merged_count = sum(1 for r in rows if r[0] == 0)
    lines.append("")
    lines.append(f"<sub>{merged_count} merged · {len(rows)} total · updated automatically</sub>")
    return "\n".join(lines)


def main() -> int:
    with open(README, encoding="utf-8") as f:
        text = f.read()
    if START not in text or END not in text:
        print(f"Markers {START} / {END} not found in {README}", file=sys.stderr)
        return 1
    new = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: f"{START}\n{build_table()}\n{END}",
        text,
        flags=re.S,
    )
    if new != text:
        with open(README, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        print("README updated")
    else:
        print("No changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
