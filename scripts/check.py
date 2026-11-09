"""Check data.js for mistakes and compare it with race results and PAC endorsement lists.

    python3 scripts/check.py            # everything
    python3 scripts/check.py --offline  # only the file checks, no downloads

Prints what differs. Exits 2 if the data files themselves have problems, 3 if only
the sources differ or couldn't be read, 0 if nothing does. (1 means the script crashed.) It never edits data.js.
Needs Python 3 with PyYAML, and Node to read data.js.
"""
import csv
import html
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "checks.yaml").read_text(encoding="utf-8"))
SUFFIXES = CONFIG["results"]["name_suffixes"]


def load_data():
    output = subprocess.run(
        ["node", str(ROOT / "scripts" / "read_data.js"), str(ROOT / "data.js")],
        capture_output=True, text=True,
    )
    if output.returncode != 0:
        print(f"**data.js could not be read, so the page is probably broken too.**\n\n{output.stderr.strip()}")
        sys.exit(2)
    return json.loads(output.stdout)


def fold(text):
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return plain.lower().replace(".", "").replace(",", "").replace("-", " ")


def surname(name):
    return [w for w in fold(name).split() if w not in {fold(s) for s in SUFFIXES}][-1]


def same_person(row_name, other_name):
    return surname(row_name) in fold(other_name).split()


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": CONFIG["user_agent"]})
    return urllib.request.urlopen(request, timeout=CONFIG["fetch_timeout"]).read().decode("utf-8")


def normal_district(text):
    text = text.upper()
    if text in CONFIG["district_aliases"]:
        return CONFIG["district_aliases"][text]
    state, seat = text.split("-")
    return f"{state}-{seat if seat == 'AL' else int(seat)}"


# ---------- file checks ----------

def check_rows(members):
    problems = []
    seen = set()
    for i, row in enumerate(members, start=1):
        label = f"Row {i} ({row.get('d', '?')} {row.get('n', '?')})"
        missing = [f for f in CONFIG["required_fields"] if f not in row]
        if missing:
            problems.append(f"{label} is missing {', '.join(missing)}.")
            continue
        if not re.match(CONFIG["district_pattern"], row["d"]):
            problems.append(f"{label}: district {row['d']!r} isn't in the form TX-32 or WY-AL.")
        if row["p"] not in CONFIG["parties"]:
            problems.append(f"{label}: party {row['p']!r} isn't one of {', '.join(CONFIG['parties'])}.")
        if row["st"] not in CONFIG["statuses"] and not row["st"].startswith(CONFIG["runoff_status_prefix"]):
            problems.append(f"{label}: status {row['st']!r} isn't one of the statuses the README lists.")
        if "lt" in row and row["lt"] not in CONFIG["tiers"]:
            problems.append(f"{label}: leadership tier {row['lt']!r} isn't 1, 2 or 3.")
        if ("lt" in row) != bool(row.get("lead")):
            problems.append(f"{label}: has a leadership tier without a role, or a role without a tier.")
        for tag in row["cau"]:
            if set(tag) != {"c", "lvl", "why"} or tag["lvl"] not in CONFIG["levels"]:
                problems.append(f"{label}: caucus entry {tag} needs c, lvl (H, M or L) and why.")
        key = (row["d"], surname(row["n"]))
        if key in seen:
            problems.append(f"{label} appears twice.")
        seen.add(key)
    return problems


def check_exports(data):
    """data.json and data.csv should carry the same rows as data.js."""
    problems = []
    exported = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    if exported["members"] != data["members"]:
        changed = [m["d"] for m, e in zip(data["members"], exported["members"]) if m != e]
        extra = abs(len(data["members"]) - len(exported["members"]))
        problems.append(
            "data.json doesn't match data.js"
            + (f" (rows differ: {', '.join(changed[:10])}{' …' if len(changed) > 10 else ''})" if changed else "")
            + (f" ({extra} rows more or fewer)" if extra else "")
            + ". Regenerate data.json and data.csv."
        )
    if exported["changelog"] != data["changelog"]:
        problems.append("The changelog in data.json doesn't match data.js. Regenerate data.json.")
    if exported["meta"].get("row_count") != len(data["members"]):
        problems.append(f"data.json says row_count {exported['meta'].get('row_count')}, but data.js has {len(data['members'])} rows.")
    with open(ROOT / "data.csv", newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    if [(r["district"], r["name"]) for r in csv_rows] != [(m["d"], m["n"]) for m in data["members"]]:
        problems.append("data.csv doesn't list the same people in the same order as data.js. Regenerate data.csv.")
    return problems


# ---------- race results ----------

def fetch_races():
    settings = CONFIG["results"]
    page = fetch(settings["url"])
    found = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not found:
        raise ValueError("the page layout changed (no __NEXT_DATA__ block)")
    props = json.loads(found[1])["props"]["pageProps"]
    races = {}
    for code, race in props["mapData"].items():
        state = race["stateCode"]
        seat = "AL" if state in settings["at_large_states"] else str(int(code[2:]))
        tip = race["tooltip"]
        races[f"{state}-{seat}"] = {
            "called": tip["callStatusCode"] == settings["called_code"],
            "percent_in": tip["percentIn"],
            "total": tip["totalVote"] or 0,
            "candidates": sorted(
                [
                    {
                        "name": c["lastName"],
                        "party": c["party"],
                        "votes": c.get("votes") or 0,
                        "incumbent": bool(c.get("isIncumbent")),
                        "winner": bool(c.get("isWinner")),
                    }
                    for c in tip["candidates"]
                ],
                key=lambda c: -c["votes"],
            ),
        }
    called = sum(r["called"] for r in races.values())
    if len(races) != settings["expected_races"] or called < settings["minimum_called"]:
        raise ValueError(f"got {len(races)} races with {called} called; the page format may have changed")
    stamp = datetime.fromisoformat(props["currentTime"].replace("Z", "+00:00")).astimezone(ZoneInfo(settings["timezone"]))
    return races, f"{stamp:%Y-%m-%d %H:%M} {settings['timezone_label']}"


def gap_text(race):
    first, second = race["candidates"][:2]
    votes = first["votes"] - second["votes"]
    points = 100 * votes / race["total"] if race["total"] else 0
    return f"{first['name']} leads {second['name']} by {votes:,} votes ({points:.1f} pts) with about {race['percent_in']:.0f}% counted"


def check_statuses(members, races):
    found = []
    label = CONFIG["results"]["label"]
    party = CONFIG["results"]["party_labels"]
    for row in members:
        race = races.get(row["d"])
        if race is None or row["st"].startswith(CONFIG["runoff_status_prefix"]):
            continue
        me = next((c for c in race["candidates"] if c["party"] == party[row["p"]] and same_person(row["n"], c["name"])), None)
        if me is None:
            found.append((row["d"], "status", f"{row['d']} {row['n']}: not among the candidates in {label}'s results."))
            continue
        winner = next((c for c in race["candidates"] if c["winner"]), None)
        if race["called"] and winner is not me:
            found.append((row["d"], "status", f"{row['d']} {row['n']}: {label} called the race for {winner['name'] if winner else 'someone else'}, so this row would come out."))
        elif race["called"] and not row["st"].startswith(CONFIG["called_prefix"]):
            found.append((row["d"], "status", f"{row['d']} {row['n']}: {label} has called the race for {me['name']}; the row says {row['st']!r}."))
        elif not race["called"]:
            leading = race["candidates"][0] is me
            expected = CONFIG["leads"] if leading else CONFIG["trails"]
            if row["st"] != expected:
                found.append((row["d"], "status", f"{row['d']} {row['n']}: {label} hasn't called it ({gap_text(race)}); the row says {row['st']!r}."))
    return found


def check_roster(members, races):
    """Anyone new who has won or leads a seat should have a row."""
    found = []
    label = CONFIG["results"]["label"]
    runoffs = {r["d"] for r in members if r["st"].startswith(CONFIG["runoff_status_prefix"])}
    for district, race in sorted(races.items()):
        if not race["candidates"] or district in runoffs:
            continue
        top = next((c for c in race["candidates"] if c["winner"]), race["candidates"][0])
        if top["incumbent"]:
            continue
        if any(r["d"] == district and same_person(r["n"], top["name"]) for r in members):
            continue
        state = "won" if race["called"] else "leads"
        found.append((district, "roster", f"{district}: {top['name']} ({top['party']}) {state} the seat in {label}'s results and isn't an incumbent, but has no row."))
    return found


def fetch_delegates():
    settings = CONFIG["delegates"]

    def api(params):
        query = urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})
        return json.loads(fetch(f"{settings['api']}?{query}"))

    sections = api({"action": "parse", "page": settings["page"], "prop": "sections"})["parse"]["sections"]
    index = next(s["index"] for s in sections if s["anchor"] == settings["section_anchor"])
    table = api({"action": "parse", "page": settings["page"], "prop": "text", "section": index})["parse"]["text"]
    delegates = {}
    for tr in re.findall(r"<tr.*?</tr>", table, re.S):
        text = re.sub(r"\[\s*\d+\s*\]", " ", re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tr))))
        place = next((p for p in settings["districts"] if text.strip().startswith(p)), None)
        if place is None:
            continue
        winner = re.search(r"Y ([^(▌]+?) \(", text)
        incumbent = re.match(rf"\s*{re.escape(place)} at-large (.+?) (Republican|Democratic|Independent)", text)
        delegates[settings["districts"][place]] = {
            "incumbent": incumbent[1] if incumbent else "",
            "winner": winner[1].strip() if winner else "",
        }
    if len(delegates) != len(settings["districts"]):
        raise ValueError(f"found {len(delegates)} of {len(settings['districts'])} delegate races")
    return delegates


def check_delegates(members, delegates):
    found = []
    for district, race in delegates.items():
        rows = [r for r in members if r["d"] == district]
        new = race["winner"] and not same_person(race["incumbent"] or "-", race["winner"])
        if new and not any(same_person(r["n"], race["winner"]) for r in rows):
            found.append((district, "delegates", f"{district}: Wikipedia shows {race['winner']} winning an open delegate seat, but there's no row."))
        for r in rows:
            if race["winner"] and not same_person(r["n"], race["winner"]):
                found.append((district, "delegates", f"{district} {r['n']}: Wikipedia shows {race['winner']} as the winner."))
            elif not race["winner"] and r["st"] == CONFIG["delegate_called"]:
                found.append((district, "delegates", f"{district} {r['n']}: marked Called, but Wikipedia shows no winner yet."))
    return found


# ---------- endorsements ----------

def page_text(url):
    raw = fetch(url)
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def read_list(source):
    text = page_text(source["url"])
    for marker in (source["start"], source["end"]):
        if marker and marker not in text:
            raise ValueError(f"the text {marker!r} that marks the list is gone; the page has probably changed")
    start = text.index(source["start"]) + len(source["start"])
    end = text.index(source["end"], start) if source["end"] else len(text)
    names = [
        {"name": m["name"].strip(), "district": normal_district(m["district"])}
        for m in re.finditer(source["pattern"], text[start:end])
    ]
    if len(names) < source["minimum"]:
        raise ValueError(f"found only {len(names)} names, expected at least {source['minimum']}")
    return names


def check_endorsements(members, source, names):
    found = []
    where = source.get("link", source["url"])
    order = CONFIG["levels"]
    for e in names:
        row = next((r for r in members if r["d"] == e["district"] and same_person(r["n"], e["name"])), None)
        if row is None:
            continue
        tag = next((t for t in row["cau"] if t["c"] == source["caucus"]), None)
        if tag is None or order.index(tag["lvl"]) > order.index(source["level"]):
            have = f"tagged {tag['lvl']}" if tag else "not tagged"
            found.append((row["d"], "endorsement", f"{row['d']} {row['n']}: endorsed by {source['source']} ({where}), but {have} for {source['caucus']}; your key says that's {source['level']}."))
    # Only tags at the level this endorsement supports rely on it. A lower tag
    # that names the source is saying it didn't endorse ("no CPC PAC endorsement found").
    for row in members:
        for tag in row["cau"]:
            if tag["c"] != source["caucus"] or source["source"] not in tag["why"] or "endors" not in tag["why"]:
                continue
            if order.index(tag["lvl"]) > order.index(source["level"]):
                continue
            if not any(same_person(row["n"], e["name"]) for e in names):
                found.append((row["d"], "endorsement", f"{row['d']} {row['n']}: the {source['caucus']} tag says {source['source']} endorsed, but the name isn't on its list now ({where})."))
    return found


# ---------- report ----------

def main():
    offline = "--offline" in sys.argv
    data = load_data()
    members = data["members"]
    file_problems = check_rows(members) + check_exports(data)
    differences, unreadable, as_of = [], [], ""
    if not offline:
        try:
            races, as_of = fetch_races()
            differences += check_statuses(members, races) + check_roster(members, races)
        except (OSError, ValueError, KeyError) as error:
            unreadable.append(f"Race results from {CONFIG['results']['url']}: {error}")
        try:
            differences += check_delegates(members, fetch_delegates())
        except (OSError, ValueError, KeyError, StopIteration) as error:
            unreadable.append(f"Delegate results from Wikipedia: {error}")
        for source in CONFIG["endorsements"]:
            try:
                differences += check_endorsements(members, source, read_list(source))
            except (OSError, ValueError) as error:
                unreadable.append(f"The {source['source']} list at {source.get('link', source['url'])}: {error}")
    known = {(k["district"], k["check"]) for k in CONFIG["known_differences"]}
    differences = [d for d in differences if (d[0], d[1]) not in known]

    lines = [f"Checked against results as of {as_of}." if as_of else "Checked the data files only.", ""]
    if file_problems:
        lines += ["**Problems in the data files**", ""] + [f"- {p}" for p in file_problems] + [""]
    if differences:
        lines += ["**Differences from the sources**", ""] + [f"- {text}" for _, _, text in sorted(set(differences))] + [""]
        lines += ["To stop reporting one you've decided to keep, add it to `known_differences` in checks.yaml.", ""]
    if unreadable:
        lines += ["**Sources that couldn't be read** (nothing was checked against these)", ""] + [f"- {u}" for u in unreadable] + [""]
    if file_problems or differences or unreadable:
        print("\n".join(lines).strip())
        sys.exit(2 if file_problems else 3)
    print("No problems found." if offline else f"No problems found. Results as of {as_of}.")


if __name__ == "__main__":
    main()
