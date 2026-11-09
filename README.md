# 120th House Freshman Tracker

New members-elect of the U.S. House for the 120th Congress (2027–29): prior legislative service, committee assignments, leadership roles, and predicted caucus memberships.

Live page: https://sorendayton.github.io/house-freshman-tracker/

## Maintainer and contact

Soren Dayton, Director of American Governance Policy, Foundation for American Innovation
Email: soren@thefai.org
Substack: Prototyping Politics

Corrections, additions, and sources are welcome by email or as a GitHub issue on this repository.

## Linking to a member

Every row has a stable anchor of the form `#state-district-lastname` (lowercase, accents and suffixes dropped), e.g. `https://sorendayton.github.io/house-freshman-tracker/#tx-30-haynes`. Opening such a link expands that member's detail row. The `anchor` column in `data.csv` lists them all.

## Disclaimer

This is an evolving work product built from open-source research (Ballotpedia, Wikipedia, press reports, caucus-PAC endorsement lists). Nothing has been validated against primary records; caucus memberships are predictions. Use it as a starting point, not a citation.

## Files

| File | What it is |
|---|---|
| `index.html` | The page. Loads `data.js` at runtime; no build step. |
| `data.js` | The dataset as a JavaScript array (`window.FRESHMEN`). This is what the page reads. |
| `data.json` | The same dataset as JSON, with a `meta` block (status date, row count). For spreadsheets and scripts. |
| `data.csv` | Flat export of the same dataset for spreadsheets: one row per member, caucus predictions as `Name (H/M/L)`, and a per-member link in the `anchor` column. |
| `og.png` | 1200×630 preview image used for link cards on X, LinkedIn, Slack, and iMessage. |
| `favicon.svg`, `apple-touch-icon.png` | Site icons. |

`data.js` is the source; `data.json` and `data.csv` are generated from it and are always in sync. `data.json` also carries a `changelog` array, which the page renders as its Updates section. To update, replace all three and `index.html` if the page changed.

## Fields (one record per member-elect or uncalled contender)

| Field | Meaning |
|---|---|
| `d` | District, e.g. `TX-32`, `WY-AL`, `DC-AL` |
| `n` | Name |
| `p` | Party, `D` or `R` |
| `st` | Race status: `Called`, `Called (D-on-D)`, `Called (delegate)`, `Uncalled — leads`, `Uncalled — trails`, `Runoff Dec 12` |
| `seat` | How the seat opened (retirement, other office, defeated incumbent, primary loss, new seat, vacancy) |
| `pred` | Predecessor |
| `leg` | Prior legislative service (state, territorial, tribal, or U.S. House), or empty |
| `lt` | Leadership tier in that legislature: `1` chamber or caucus leadership, `2` committee chair or ranking member, `3` vice chair or subcommittee chair; absent if none |
| `lead` | Description of the leadership role |
| `comm` | Committee assignments, most recent session first (Ballotpedia) |
| `other` | Other offices and career |
| `cau` | Predicted ideological caucuses: array of `{c: caucus, lvl: H/M/L, why: basis}` |
| `ident` | Likely identity or affinity caucuses (inferred from reported background) |
| `note` | Caveats, race margins, recount status |

Confidence levels: `H` endorsement by the caucus's own PAC, prior membership, or self-identification; `M` inference from record, district, or allied-group endorsement; `L` guess.

Returning former members (Carl, Solis, Bean, Allred, Luria, McAdams) are included and flagged in `seat`. Contenders are removed once their race is called against them.

## Sources

Election results: Wikipedia's 2026 House elections results tables; Ballotpedia; AP and local reporting for recounts. Bios and committees: Ballotpedia and Wikipedia. Caucus signals: NewDem Action Fund, Blue Dog PAC, Freedom Caucus Fund, Republican Main Street PAC, Congressional Progressive Caucus PAC, Justice Democrats; FEC filings for the Republican Governance Group PAC. Full source list is in the page's method note.

## Checks

`scripts/check.py` reads `data.js` and reports:

- rows with a missing field, an unknown status or confidence level, or a leadership tier without a role
- `data.json` or `data.csv` out of step with `data.js`
- statuses that differ from NBC's race calls, and new winners or leaders with no row
- delegate races that differ from Wikipedia's results table
- PAC endorsements that the tags don't reflect, and H tags citing an endorsement that isn't on the PAC's list

It never edits anything. Run it with `python3 scripts/check.py` (needs PyYAML and Node), or `--offline` to skip the downloads. A GitHub Action runs it on every push and every three hours, and keeps one issue open listing whatever differs; the issue closes itself when nothing does. Source URLs, page markers and allowed values are in `checks.yaml`. To stop reporting a difference you've decided to keep, add it to `known_differences` there.
