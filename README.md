# Empty Ballot Lines

A dashboard of every 2026 state legislative race in the 46 states holding elections (88 chambers, about 6,100 seats), showing which seats have no Democrat-vs-Republican race and which have no opponent at all.

- `pipeline/states.py` reads official candidate lists from state election offices (CO, DE, FL, MN, NM). Add a state by writing a reader that returns `(chamber, district, name, party)` rows and listing it in `SOURCES`.
- `pipeline/build.py` uses a state's official list when it has one, otherwise the chamber's "2026 ⟨State⟩ ⟨Chamber⟩ election" page on Wikipedia, and writes `site/data/seats.json` and `seats.csv`.
- `site/` is a static D3 page: national totals, a state map, a sortable state table, and a drill-down to every district and candidate.
- `.github/workflows/refresh.yml` runs the tests and the pipeline daily, commits the new data, and deploys `site/` to GitHub Pages.

## Set up

1. Create a GitHub repo and push this folder to `main`.
2. In the repo, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
3. The push starts the workflow. When it finishes (about 3 minutes), the dashboard is live at `https://<user>.github.io/<repo>/`.

To refresh by hand, use **Actions → Refresh data and deploy → Run workflow**.

## Run locally

```sh
pip install -r requirements.txt
python -m unittest discover -s tests
python pipeline/build.py          # ~2 minutes; prints races and seats per chamber
python -m http.server -d site 8000  # then open http://localhost:8000
```

## How seats are classified

Each race gets one category:

| Category | Meaning |
|---|---|
| `two_party` | A Democrat and a Republican are both on the ballot |
| `one_party` | More candidates than seats, but not both major parties (an independent opponent, or two candidates of the same party in a top-two state) |
| `unopposed` | No more candidates than seats |
| `unknown` | The page lists no candidates yet; left out of all percentages |

"No D vs. R race" = `one_party` + `unopposed`, the same idea as Ballotpedia's major-party competition measure. Write-ins are dropped. Fusion and cross-nominated candidates count as the first major party in their label. Multi-member districts count every seat.

## Data quality

Wikipedia pages are not uniform, so the parser has two strategies:

1. **District table** (most pages): the table whose first column is the district and which has a "Candidates" column. Rowspans are expanded, so multi-member and position-numbered districts come out right.
2. **District sections** (e.g. the Tennessee Senate page): the election infobox under each "District N" heading. A primary-only box counts as unopposed only when the page says no other party filed.

Safeguards:
- If a chamber page fails to load or parse, its last good data is kept and marked stale.
- The run aborts without overwriting anything if nothing parses.
- The dashboard lists every chamber that is missing, stale, or has unlisted seats.

After the first run, check the coverage notes at the bottom of the dashboard and the per-chamber counts in the Action log against known seat totals. A chamber with 0 races needs either a corrected page title in `CHAMBERS` or a third parsing strategy.

Candidate data is from Wikipedia (CC BY-SA 4.0); keep that attribution if you redistribute `site/data`.
