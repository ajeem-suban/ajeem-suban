#!/usr/bin/env python3
"""Generate self-hosted forensic GitHub profile SVG cards using only Python stdlib."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "assets" / "cards"
OWNER = os.getenv("PROFILE_LOGIN", "ajeem-suban")
TOKEN = os.getenv("GITHUB_TOKEN")
API = "https://api.github.com/graphql"
BG, PANEL, RED, TEXT, MUTED, GRID = "#0A0A0B", "#111114", "#E01B24", "#E6EDF3", "#8B949E", "#29292F"

QUERY = """
query ProfileForensics($login: String!) {
  user(login: $login) {
    login name url followers { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name nameWithOwner stargazerCount forkCount
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}
"""

UPSTREAM_QUERY = """
query Upstream($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    issueCount
    edges {
      node {
        ... on PullRequest {
          state mergedAt
          repository { nameWithOwner stargazerCount }
        }
      }
    }
  }
}
"""

def graphql(query: str, variables: dict) -> dict:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=payload, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "ajeem-forensic-profile-generator",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc
    if body.get("errors"):
        raise RuntimeError("GitHub GraphQL errors: " + json.dumps(body["errors"]))
    return body["data"]

def svg_start(title: str, subtitle: str = "", width: int = 490, height: int = 180) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" rx="12" fill="{BG}" stroke="{GRID}"/>'
        f'<text x="22" y="30" fill="{RED}" font-family="monospace" font-size="12" font-weight="700" letter-spacing="1.4">{escape(title.upper())}</text>'
        + (f'<text x="22" y="49" fill="{MUTED}" font-family="sans-serif" font-size="10">{escape(subtitle)}</text>' if subtitle else "")
    )

def svg_end() -> str:
    return "</svg>"

def txt(x, y, value, size=13, color=TEXT, weight="400", family="sans-serif"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="{family}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'

def rect(x, y, w, h, color, rx=4):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{color}"/>'

def save(name: str, body: str):
    CARDS.mkdir(parents=True, exist_ok=True)
    (CARDS / name).write_text(body + "\n", encoding="utf-8")

def contribution_days(user):
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [d for w in weeks for d in w["contributionDays"]]

def streaks(days):
    rows = sorted(days, key=lambda x: x["date"])
    counts = {date.fromisoformat(x["date"]): x["contributionCount"] for x in rows}
    today = datetime.now(timezone.utc).date()
    cursor = today if counts.get(today, 0) else today - timedelta(days=1)
    current = 0
    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    best = run = 0
    previous = None
    for d in sorted(counts):
        if counts[d] > 0:
            run = run + 1 if previous and d == previous + timedelta(days=1) else 1
            best = max(best, run)
            previous = d
        else:
            run = 0
            previous = d
    active = sum(1 for v in counts.values() if v > 0)
    return current, best, active

def render_dossier(user, days, repos):
    c = user["contributionsCollection"]
    total = c["contributionCalendar"]["totalContributions"]
    current, longest, active = streaks(days)
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    metrics = [
        ("CONTRIBUTIONS", total), ("PUBLIC REPOS", user["repositories"]["totalCount"]),
        ("STARS EARNED", stars), ("FORKS OF WORK", forks),
        ("FOLLOWERS", user["followers"]["totalCount"]), ("CURRENT STREAK", f"{current} DAYS"),
    ]
    s = svg_start("CASE FILE // SUBJECT DOSSIER", f"@{OWNER}  •  LIVE GITHUB DATA", 490, 190)
    for i, (label, value) in enumerate(metrics):
        col, row = i % 3, i // 3
        x, y = 22 + col * 155, 88 + row * 65
        s += rect(x, y - 25, 140, 48, PANEL, 7)
        s += txt(x + 11, y - 7, label, 9, MUTED, "700", "monospace")
        s += txt(x + 11, y + 12, value, 17, TEXT, "700")
    s += txt(22, 177, f"LONGEST STREAK: {longest} DAYS   •   ACTIVE DAYS: {active}", 9, MUTED, "700", "monospace")
    save("dossier.svg", s + svg_end())

def render_languages(repos):
    totals = Counter()
    colors = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] += edge["size"]
            colors[name] = edge["node"].get("color") or RED
    top = totals.most_common(6)
    maximum = max((v for _, v in top), default=1)
    s = svg_start("LANGUAGE FORENSICS", "Byte distribution across public, non-fork repositories", 490, 205)
    for i, (name, value) in enumerate(top):
        y = 79 + i * 20
        s += txt(22, y, name, 11, TEXT)
        s += rect(125, y - 10, 260, 8, GRID, 4)
        s += rect(125, y - 10, max(2, 260 * value / maximum), 8, colors[name], 4)
        s += txt(398, y, f"{100*value/max(1,sum(totals.values())):.1f}%", 10, MUTED, "400", "monospace")
    save("languages.svg", s + svg_end())

def render_streak(days):
    current, longest, active = streaks(days)
    s = svg_start("COMMIT STREAK // FIELD RECORD", "Contribution consistency, calculated from the GitHub calendar", 490, 180)
    for x, label, value in [(28, "CURRENT", current), (190, "LONGEST", longest), (352, "ACTIVE DAYS", active)]:
        s += txt(x, 100, str(value), 34, TEXT, "700")
        s += txt(x, 123, label, 10, RED, "700", "monospace")
    s += txt(28, 155, "A day counts when GitHub records at least one contribution.", 10, MUTED)
    save("streak.svg", s + svg_end())

def render_mix(user):
    c = user["contributionsCollection"]
    values = [
        ("Commits", c["totalCommitContributions"], "#E01B24"),
        ("Pull requests", c["totalPullRequestContributions"], "#F97316"),
        ("Issues", c["totalIssueContributions"], "#EAB308"),
        ("Repositories", c["totalRepositoryContributions"], "#8B5CF6"),
    ]
    total = sum(v for _, v, _ in values) or 1
    cx, cy, radius, circumference = 105, 108, 52, 2 * 3.141592653589793 * 52
    offset = 0
    s = svg_start("CONTRIBUTION MIX", "Contribution categories from the current GitHub contribution year", 490, 205)
    for label, value, color in values:
        length = circumference * value / total
        s += f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="15" stroke-dasharray="{length:.2f} {circumference-length:.2f}" stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        offset += length
    s += txt(79, 112, f"{total}", 17, TEXT, "700")
    for i, (label, value, color) in enumerate(values):
        y = 77 + i * 27
        s += rect(210, y - 10, 9, 9, color, 2)
        s += txt(229, y, label, 11)
        s += txt(425, y, f"{value:,}  ({100*value/total:.1f}%)", 10, MUTED, "400", "monospace")
    save("chart-donut.svg", s + svg_end())

def render_monthly(days):
    now = datetime.now(timezone.utc).date()
    months = []
    for offset in range(11, -1, -1):
        year, month = now.year, now.month - offset
        while month <= 0:
            year -= 1
            month += 12
        months.append((year, month))
    counts = Counter()
    for item in days:
        d = date.fromisoformat(item["date"])
        counts[(d.year, d.month)] += item["contributionCount"]
    vals = [counts[m] for m in months]
    maximum = max(vals, default=1) or 1
    s = svg_start("VOLUME ANALYSIS // MONTHLY", "Contributions per month • trailing 12 months", 700, 220)
    points = []
    for i, value in enumerate(vals):
        x = 35 + i * 56
        y = 174 - (value / maximum) * 100
        points.append(f"{x},{y:.1f}")
        s += txt(x - 12, 195, date(months[i][0], months[i][1], 1).strftime("%b").upper(), 9, MUTED, "400", "monospace")
        s += txt(x - 8, y - 8, value, 9, TEXT, "700", "monospace")
    s += f'<polyline points="{" ".join(points)}" fill="none" stroke="{RED}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
    for point in points:
        x, y = point.split(",")
        s += f'<circle cx="{x}" cy="{y}" r="3.5" fill="{RED}"/>'
    s += f'<path d="M {points[0]} L {" L ".join(points[1:])} L 651,180 L 35,180 Z" fill="{RED}" opacity="0.12"/>'
    save("chart-area.svg", s + svg_end())

def render_weekdays(days):
    totals = Counter()
    for d in days:
        totals[d["weekday"]] += d["contributionCount"]
    labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    maximum = max(totals.values(), default=1) or 1
    s = svg_start("WEEKDAY RHYTHM", "Contribution distribution by day of week", 490, 205)
    for i, label in enumerate(labels):
        value = totals[i]
        y = 77 + i * 17
        s += txt(22, y, label, 10, TEXT)
        s += rect(75, y - 9, 315, 7, GRID, 3)
        s += rect(75, y - 9, 315 * value / maximum, 7, RED, 3)
        s += txt(405, y, value, 9, MUTED, "400", "monospace")
    save("chart-bars.svg", s + svg_end())

def render_heatmap(days):
    rows = sorted(days, key=lambda x: x["date"])[-371:]
    maxv = max((d["contributionCount"] for d in rows), default=1) or 1
    s = svg_start("CONTRIBUTION SPATTER // 52 WEEKS", "Daily contribution intensity • GitHub contribution calendar", 900, 150)
    for i, d in enumerate(rows):
        col, row = divmod(i, 7)
        value = d["contributionCount"]
        color = "#17171B" if value == 0 else ("#641015" if value/maxv < .25 else "#A3161D" if value/maxv < .5 else "#D21E27" if value/maxv < .8 else RED)
        s += rect(20 + col * 16, 63 + row * 11, 10, 8, color, 2)
    s += txt(20, 143, "LESS", 8, MUTED, "700", "monospace")
    for i, color in enumerate(["#17171B", "#641015", "#A3161D", "#D21E27", RED]):
        s += rect(55 + i * 14, 133, 10, 8, color, 2)
    s += txt(135, 143, "MORE", 8, MUTED, "700", "monospace")
    save("heatmap.svg", s + svg_end())

def render_repos(repos):
    top = sorted(repos, key=lambda r: (r["stargazerCount"], r["forkCount"]), reverse=True)[:5]
    s = svg_start("TOP REPOSITORIES // EVIDENCE", "Ranked by stars, then forks • public non-fork repositories", 700, 205)
    for i, repo in enumerate(top):
        y = 78 + i * 25
        s += txt(22, y, f"0{i+1}", 10, RED, "700", "monospace")
        s += txt(55, y, repo["name"], 11, TEXT, "700")
        lang = (repo.get("primaryLanguage") or {}).get("name") or "—"
        s += txt(390, y, lang, 9, MUTED)
        s += txt(545, y, f"★ {repo['stargazerCount']}   ⑂ {repo['forkCount']}", 10, TEXT, "400", "monospace")
    save("repos.svg", s + svg_end())

def fetch_upstream():
    try:
        data = graphql(UPSTREAM_QUERY, {"q": f"author:{OWNER} is:pr"})
        edges = data["search"]["edges"]
    except Exception as exc:
        print(f"WARNING: upstream PR search unavailable: {exc}", file=sys.stderr)
        return []
    grouped = defaultdict(lambda: {"merged": 0, "open": 0, "closed": 0, "stars": 0})
    for edge in edges:
        node = edge.get("node") or {}
        repo = node.get("repository") or {}
        name = repo.get("nameWithOwner")
        if not name:
            continue
        state = (node.get("state") or "CLOSED").lower()
        bucket = grouped[name]
        bucket["stars"] = repo.get("stargazerCount") or 0
        if node.get("mergedAt"):
            bucket["merged"] += 1
        elif state == "open":
            bucket["open"] += 1
        else:
            bucket["closed"] += 1
    return sorted(grouped.items(), key=lambda item: (item[1]["merged"], item[1]["stars"]), reverse=True)[:6]

def render_upstream(items):
    s = svg_start("UPSTREAM CONTRIBUTIONS // FIELD WORK", "Public pull requests authored by this account • top repositories", 700, 205)
    if not items:
        s += txt(22, 91, "No public upstream pull requests were returned by GitHub search.", 12, TEXT)
        s += txt(22, 116, "This is a data result, not an assumed zero for private activity.", 10, MUTED)
    else:
        s += txt(22, 61, "PROJECT", 9, RED, "700", "monospace")
        s += txt(445, 61, "MERGED", 9, RED, "700", "monospace")
        s += txt(525, 61, "OPEN", 9, RED, "700", "monospace")
        s += txt(585, 61, "CLOSED", 9, RED, "700", "monospace")
        for i, (name, counts) in enumerate(items):
            y = 87 + i * 21
            s += txt(22, y, name, 10, TEXT)
            s += txt(455, y, counts["merged"], 10, TEXT, "700", "monospace")
            s += txt(535, y, counts["open"], 10, TEXT, "400", "monospace")
            s += txt(595, y, counts["closed"], 10, TEXT, "400", "monospace")
    save("upstream.svg", s + svg_end())

def render_quote():
    s = svg_start("THE CODE // DAILY PRINCIPLE", "A note from the engineering archive", 900, 120)
    s += txt(25, 76, "RESEARCH.  ENGINEER.  EVALUATE.  EVOLVE.", 23, TEXT, "700", "monospace")
    save("quote.svg", s + svg_end())

def main():
    if not TOKEN:
        print("ERROR: Set GITHUB_TOKEN before running.", file=sys.stderr)
        return 2
    data = graphql(QUERY, {"login": OWNER})
    user = data["user"]
    if not user:
        raise RuntimeError(f"GitHub user not found: {OWNER}")
    days = contribution_days(user)
    repos = user["repositories"]["nodes"]
    render_dossier(user, days, repos)
    render_languages(repos)
    render_streak(days)
    render_mix(user)
    render_monthly(days)
    render_weekdays(days)
    render_heatmap(days)
    render_repos(repos)
    upstream = fetch_upstream()
    render_upstream(upstream)
    render_quote()
    summary = {
        "login": user["login"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "public_repositories": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
    }
    (ROOT / "profile-data.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(list(CARDS.glob('*.svg')))} SVG cards for @{OWNER}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
