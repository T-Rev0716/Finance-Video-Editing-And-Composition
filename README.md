# Video Prep Studio

Turns one finance or AI news topic into everything you need to record a 5-15 minute YouTube
video and 3-5 TikTok clips:

1. **Fact sheet** - every claim with its source link. News-only numbers are flagged "verify".
2. **Real charts** - 3-6 charts from public data, as 1920x1080 and 1080x1920 PNGs.
3. **Outline** - bullet points in your structure (hook, what happened, why, what it means for
   you, what to watch, closing), with chart and visual markers.
4. **Shot list** - talking head, chart, headline screenshot or B-roll for each scene, with
   Higgsfield prompts.
5. **Titles and thumbnails** - 8 titles (60 characters or fewer), 3 thumbnail texts (4 words
   or fewer), next to the competitor outlier titles from your report.
6. **Clip plan** - upload the recorded video's transcript and get 3-5 self-contained
   30-60 second clips with timestamps and caption hooks.
7. **Compliance checklist** and a ready-to-paste **YouTube description** with sources and
   the disclaimer.

It runs on your own computer. Nothing is uploaded anywhere except the data requests listed
under [Where the numbers come from](#where-the-numbers-come-from) and, if you add a key, the
wording request to the LLM.

## Quick start (Windows)

You need Python 3.10 or newer ([python.org](https://www.python.org/downloads/); tick "Add
Python to PATH" in the installer).

```bat
pip install -r requirements.txt
python app.py
```

Your browser opens at <http://127.0.0.1:8000>. To stop the app, press Ctrl+C in the window
where it is running. You can also double-click `run.bat`.

Then:

1. Put your script's daily reports in `reports/` (a sample is included so you can try it now).
2. On **Topics**, click a theme card or type your own topic, then **Generate package**.
3. Open the tabs: Fact sheet, Charts, Outline, Shot list, Titles & thumbnails, Clip plan,
   Compliance, Description. **Download ZIP** exports the whole project.

Generating takes roughly 30-60 seconds without an LLM key and a couple of minutes with one.

## See a real run first

`examples/demo-run/` is an actual package generated on 2026-11-17 from live FRED data for the
topic "Mortgage rates back above 7% as the 10-year Treasury yield tops 5%": six charts in
both sizes, a 28-item fact sheet, outline, shot list, titles, description, compliance
checklist and a clip plan. It was made **without** an LLM key, so the wording is the built-in
templates. `examples/screenshots/` shows the app during that run.

## Keys (all optional)

Open **Settings** in the app and paste keys there. They are written to a `.env` file next to
`app.py` (see `.env.example`). `.env` is in `.gitignore`; keys are never hard-coded and the
app never shows a saved key again, only its last four characters.

| Key | What it adds | Without it |
| --- | --- | --- |
| FRED API key ([free](https://fred.stlouisfed.org/docs/api/api_key.html)) | Upcoming release dates for "what to watch next"; series titles for custom series | Data still loads through FRED's public CSV download. Release dates are left blank with a link to the official schedule. |
| Anthropic API key | Better wording for the outline, titles, thumbnails and B-roll prompts | Built-in templates write the wording from the fact sheet. |
| BLS API key ([free](https://data.bls.gov/registrationEngine/)) | A higher daily limit for cross-checking BLS numbers at the source | The keyless limit is small; if it is hit the cross-check is skipped and says so. |
| SEC contact | The SEC asks tools to identify themselves ("Your Name you@example.com") | A generic name is sent. |

## The report format

The app reads the newest `reports/*.json` (by the date in the file name, e.g.
`2026-11-16.json`). Expected shape:

```json
{
  "themes": [
    {
      "theme": "Mortgage rates back above 7%",
      "score": 92,
      "open_lane": true,
      "headlines": [{"title": "...", "link": "https://..."}],
      "search_trends": ["mortgage rates today"],
      "competitor_videos": [{"title": "...", "channel": "...", "views": 1200000, "url": "https://..."}]
    }
  ],
  "tickers": ["NVDA"],
  "emerging": ["term premium"],
  "competitor_outliers": [{"title": "...", "channel": "...", "views": 2500000, "url": "https://..."}]
}
```

The loader is forgiving: headlines can be plain strings; `link`/`url`, `views`/`view_count`
and `"1.2M"`-style view counts are all accepted. The loader was written from this description
rather than from one of your real files, so if a field from your script does not show up,
that is the place to adjust (`vps/reports.py`).

`reports/2026-11-16.json` is a **sample** built by hand from web searches so there is
something to click. Its headlines and links are real; its scores are placeholders and it has
no view counts. Delete it once your own reports are in the folder.

## Where the numbers come from

| Source | Used for | Key needed |
| --- | --- | --- |
| [FRED](https://fred.stlouisfed.org/) (St. Louis Fed) | Rates, yields, mortgage rates, CPI, unemployment, payrolls, oil, gas, S&P 500, Nasdaq, GDP and more. FRED republishes each agency's numbers; the chart credit names the agency. | No (optional) |
| [BLS API](https://www.bls.gov/developers/) | Cross-checks CPI and unemployment against the Bureau of Labor Statistics directly | No (optional) |
| [Treasury Fiscal Data](https://fiscaldata.treasury.gov/) | National debt (Debt to the Penny), average interest rate on federal debt | No |
| [SEC EDGAR](https://www.sec.gov/edgar) | Company filings (10-K, 10-Q, 8-K links) and annual revenue, net income and capital spending from 10-K data | No |

Which charts a topic gets is decided by keyword rules in `vps/catalog.py` (13 topic
families, 38 charts). You can add up to four extra FRED series IDs on the Topics page.

### How "never make up a number" is enforced

- All numbers are fetched by code (`vps/sources/`) or computed from fetched numbers
  (`vps/transforms.py`). The fact sheet sentences are assembled by code (`vps/facts.py`).
- The LLM never types a number. It is given the fact sheet and writes placeholders such as
  `{F7}`; `vps/numbers.py` inserts the fetched value and **deletes any other number** the
  model wrote. Deleted numbers are listed on the Compliance tab.
- A title or thumbnail with a stray number is dropped, not patched.
- If a source fails or a month was never published, that fact or chart is skipped and listed
  under "data notes". Nothing is estimated or interpolated.
- Headlines from your report are quoted as "Reported: ..." and always flagged **verify**.
- The raw data behind every chart is saved in the project's `data/` folder as CSV.

## Compliance

Every package gets the same checklist (`vps/compliance.py`):

- Automatic: no buy/sell recommendations, no price targets, no promises of returns (pattern
  scans over every generated line), disclaimer present, AI visuals labelled and disclosed,
  sources listed in the description, every number traced to the fact sheet, news-only claims
  flagged.
- Manual: seven boxes only you can tick, because you speak freestyle (for example "I said the
  disclaimer out loud").

B-roll prompts are always generic and symbolic. A prompt that names a real person or office
(a Fed chair, a president, a CEO) or asks for news-style footage is **blocked**: it gets no
prompt text and fails the checklist until rewritten. Every AI visual carries the label
"ILLUSTRATIVE - AI-generated", and the description includes an AI disclosure.

The pattern scans catch common advice phrasing; they are a safety net, not a legal review.
The disclaimer text is editable in Settings.

## Project folders

Everything is stored locally, one folder per video:

```
projects/2026-11-17_mortgage-rates-back-above-7/
  project.json                 everything, machine-readable
  fact_sheet.md
  outline.md
  shot_list.md                 includes the Higgsfield prompts
  titles_and_thumbnails.md
  youtube_description.txt
  compliance_checklist.md
  clip_plan.md                 after you upload a transcript
  transcript.srt
  charts/chart_01_..._1920x1080.png, chart_01_..._1080x1920.png, ...
  data/MORTGAGE30US.csv, ...   the raw numbers behind the charts
```

## Tests

```bat
python -m pytest
```

116 tests, none of which use the network. They cover the data-fetch functions (parsing,
key and no-key paths, fallbacks, error handling), chart rendering (exact pixel sizes, both
orientations, every chart kind), the number guard, compliance rules, the clip planner, the
full pipeline and the web API.

## Good to know

- **S&P 500 history:** FRED currently serves only about one year of S&P 500 closes, so the
  S&P chart covers a year. The Nasdaq Composite chart goes back further.
- **Gold:** FRED no longer carries a daily gold price. The gold chart uses the BLS export
  price index for gold, which is labelled as an index, not a dollar price.
- **Fed meeting dates** come from `data/fomc_meetings.json`, which holds the 2026 calendar.
  They are always shown with a "verify" note and a link to the Fed's page. Add the next
  year's dates to that file when the Fed publishes them.
- **Behind a firewall or VPN?** If a source is blocked the app says which one and carries on
  with what it could fetch. If nothing can be fetched, generation stops with an error
  instead of producing an empty package.
- **Offline:** responses are cached for an hour in `.cache/`. Set the environment variable
  `VPS_CACHE_TTL` (seconds) to keep working from the last fetch.
- The app listens on `127.0.0.1` only, so it is not reachable from other devices.

## Code map

```
app.py                 start here: python app.py
vps/server.py          web API (FastAPI)
vps/pipeline.py        the Generate button, end to end
vps/catalog.py         series, charts and topic families (configuration, no numbers)
vps/topics.py          topic -> which charts
vps/sources/           FRED, BLS, Treasury, SEC EDGAR, shared HTTP layer
vps/builder.py         fetch data, draw charts, build the fact sheet
vps/facts.py           fact sentences, built by code
vps/charts.py          chart rendering (matplotlib)
vps/wording.py         built-in template wording
vps/voice.py           plain-English lines and B-roll ideas for the templates
vps/llm.py             optional LLM wording (Anthropic API)
vps/numbers.py         the number guard
vps/package.py         outline, shot list, titles, description
vps/compliance.py      checklist rules
vps/clips.py           transcript -> clip plan
vps/projects.py        project folders and ZIP export
web/                   the front end (plain HTML, CSS, JavaScript)
tests/
```
