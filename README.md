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

And a creator studio around that package:

- **Recording cards** you rewrite in your own voice, with the sourced numbers pinned to each
  card, a camera-line recording view, and chapter / `.edl` / `.fcpxml` exports.
- **Visual asset board**: drop local files onto scenes, track what is missing, reuse clips
  across episodes.
- **Thumbnail workshop** with a phone-size preview, and **explanation graphics** (animated
  line reveal, highlighted date, comparison card, flow diagram).
- **"What changed since I recorded?"**: freeze the facts, re-check later, decide fact by fact.
- **Learning log** of what you published and how it did.
- **Local post-production**: transcription, spoken fact-check, dead-air stripping, 9:16 shorts.

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
where it is running.

**Easier:** double-click `run.bat`. It finds Python even when it is not on PATH and installs
the packages the first time. To get a Desktop icon, double-click
`Create Desktop Shortcut.bat` once; after that, open **Video Prep Studio** from your Desktop.
Don't move the project folder afterwards (or just run the shortcut file again).

Then:

1. Put your script's daily reports in `reports/` (a sample is included so you can try it now).
2. On **Topics**, click a theme card or type your own topic, then **Generate package**.
3. Open the tabs: Fact sheet, Charts, Outline, Shot list, Titles & thumbnails, Clip plan,
   Compliance, Description. **Download ZIP** exports the whole project.

Generating takes roughly 30-60 seconds without an LLM key and a couple of minutes with one.

## See a real run first

`examples/demo-run/` is an actual package generated on 2026-11-17 from live FRED data for the
topic "Mortgage rates back above 7% as the 10-year Treasury yield tops 5%": six charts, a
28-item fact sheet, recording cards, asset board, two thumbnails, four explanation graphics
(including the `.mp4` reveal) and a learning-log entry. It was made **without** an LLM key, so
the wording is the built-in templates, and the presenter photo is a placeholder shape.
`examples/screenshots/` shows the app during that run.

## Creator studio

### Recording cards (tab: Recording cards)

One large card per outline section. Each card has:

- **Main point**, editable in your own words. Edits save as you type.
- **Pinned essential numbers**: the exact verified values, their dates and source links.
  They are stored separately from the wording, so rewriting a card never loses them. Click a
  pinned number to insert it at the cursor.
- **Live checks**: every edit runs the number guard and the compliance scan. A digit that is
  not on the fact sheet, or a phrase that reads like advice, gets a warning under the card.
  The app warns; it never rewrites what you typed.
- **Pronunciation and delivery notes**, and a preview of the card's chart, headline or B-roll.
- Reorder (drag the handle, or the arrow buttons), mark `Not recorded` / `Recorded` /
  `Needs another take`, and **Undo / Redo** (50 steps, wording and pinned sources included).

**Launch recording view** docks the active card at the top-centre of the screen, under your
webcam. Press `Space` when you hit record, then:

| Key | What it does |
| --- | --- |
| `Space` | Next card. Logs the timestamp and marks the card you just finished as recorded. |
| `R` | Redo this card. Flags the take, marks the card "needs another take", starts a new take. |
| `Esc` | Finish and save the cue log. |

After a take, export **YouTube chapters**, a CMX3600 **`.edl`** and an **`.fcpxml`** from the
links at the top of the tab. Flagged takes are left out of the timelines.

### Visual asset board (tab: Asset board)

Every scene in the shot list gets a slot. Charts are linked automatically. For headlines and
B-roll, drag a `.mp4 .mov .webm .png .jpg .gif` from your computer onto the scene (or browse).
The bar at the top reads "X of Y scene visuals ready - Z missing"; tick **Missing only** to
see what is left. Tick **Save to reusable library** to keep an intro or evergreen clip for
later episodes, and **Pick from library** to drop one in. Files are copied into the project's
`assets/` folder; nothing is uploaded anywhere.

### Thumbnail workshop (tab: Titles & thumbnails)

Four 1280x720 layouts (chart hero + host, split comparison, big stat badge, minimal
editorial) in four colour themes. Upload a few photos of yourself once (a transparent PNG
cutout works best), pick a chart or a background image, and type a headline of four words or
fewer. Type `{F1}` to drop in a verified number; any other number, or advice-style wording,
is refused. Every thumbnail is shown full size with **Download PNG** and at **phone-feed size
(168x94)** beside your title and channel name, with the measured height of the headline
letters at that size. Save a layout + colour + photo combination as a named preset.

### Explanation graphics (tab: Charts & graphics)

Built from the same data as the charts, in 1920x1080 and 1080x1920, with the source line:

1. **Line-chart reveal**: the line draws in left to right, then holds on the final value
   (5 seconds, `.mp4` with ffmpeg, half-size `.gif` without).
2. **Highlighted date + callout**: pick the peak, the low, the latest value or a date; the
   chart is redrawn with an event line, arrow and label. The axes and scale do not change.
3. **Side-by-side comparison**: two facts, or one series on two dates.
4. **Mechanism flow** (A -> B -> C): three or four boxes; `{F1}` puts a verified number in a box.

### What changed since I recorded? (tab: Fact sheet)

**Freeze facts now** saves the facts and the last observation of every data file (it also
happens automatically the first time you mark a card recorded). **Check for changes**
re-fetches everything into a `staging/` folder and lists each fact whose value, date or
revision changed, with every card, chart, graphic, thumbnail and description line that uses
it. For each fact you choose:

- **Keep frozen as-recorded value**: a date note is added to the affected cards and to the
  description.
- **Accept new value**: the fact sheet and charts are updated and the affected cards are
  flagged "needs another take".

Your card wording is never rewritten either way, and the package as it stood is copied to
`versions/` first.

### Learning log (tab: Learning log)

One record per episode: hook, final title, thumbnail layout, topic family, open-lane or not,
minutes spent, and the results you enter after publishing. The summary shows counts and
medians of your own episodes. Anything based on fewer than eight episodes is labelled
**TENTATIVE - small sample size (N episodes)**. There is no predicted or "viral" score.

### Local post-production (tab: Clip plan)

- Add the recording (`.mp4 .mov .mkv .wav .mp3`) by upload or by pasting its path, or upload
  a `.srt` / `.txt` transcript.
- **Transcribe on this computer** uses `faster-whisper` (GPU if you have one).
- **Spoken fact-check**: every number you said is compared with the fact sheet. Exact
  matches pass; rounded versions ("about 7 percent" for 7.11%) are listed as rounded;
  anything else is flagged with its timestamp so you can cut or verify it.
- **Strip dead air** removes silences longer than 0.45 s (adjustable) into a new file; the
  original is never touched.
- **Export 9:16 Short** per planned clip: chart on top, camera crop below, captions burned in.

### Optional tools

None of these are required. The app says what is missing and falls back.

| Tool | Used for | Without it |
| --- | --- | --- |
| [ffmpeg](https://ffmpeg.org/download.html) on PATH | `.mp4` reveal animations, dead-air cuts, 9:16 shorts | Reveal becomes a `.gif`; dead air works for `.wav` only (otherwise a cut list); shorts export the captions `.srt` and cut times |
| `pip install faster-whisper` | Local transcription | Upload an `.srt` or `.txt` instead |
| [Ollama](https://ollama.com/) | Free local wording | Built-in templates (or the Anthropic API) |

**Local Ollama wording:** in Settings choose *Local Ollama* as the wording engine and enter
the exact model tag from `ollama list`. If the tag is left blank, the app uses the first
installed model with "qwen" in its name. Local models go through exactly the same number
guard and compliance checks as any other engine.

**Topic radar:** the *Import latest topic radar* button on the Topics page copies the newest
report from the folder named in Settings.

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
  fact_sheet.md, outline.md, shot_list.md, titles_and_thumbnails.md
  youtube_description.txt, compliance_checklist.md, clip_plan.md
  recording_cards.json         your edited cards, undo history and cue log
  asset_board.json             which file fills which scene
  frozen_facts.json            the facts as recorded
  fact_changes.json            the latest change report
  learning_log.json
  charts/                      PNGs plus the plotted data of each chart (.json)
  data/                        the raw numbers behind the charts (.csv)
  assets/                      files you imported for scenes
  thumbnails/                  thumb_01.png, thumb_01_phone.png, ...
  graphics/                    explanation graphics
  timeline/                    chapters.txt, timeline.edl, timeline.fcpxml
  shorts/                      9:16 exports and caption files
  versions/                    the package as it stood before each accepted change
  recording/, staging/         raw recording and re-fetch scratch area (left out of the ZIP)
```

Shared across episodes, next to `app.py`: `assets/hosts/` (your photos), `assets/library/`
(reusable clips), `assets/thumbnail_presets.json` and `data/learning_log.json`.

## Tests

```bat
python -m pytest
```

208 tests, none of which use the network. They cover the data-fetch functions (parsing,
key and no-key paths, fallbacks, error handling), chart rendering (exact pixel sizes, both
orientations, every chart kind), the number guard, compliance rules, the clip planner, the
full pipeline and the web API, plus the studio features: recording-card edits, undo and
number guard, asset-board slots and library, thumbnail layouts and phone-preview data,
explanation graphics, fact-freeze diffing, learning-log tentative labels, the spoken
fact-check and the Ollama number guard. Tests that need ffmpeg run only where it is installed.

## Good to know

- **S&P 500 history:** FRED currently serves only about one year of S&P 500 closes, so the
  S&P chart covers a year. The Nasdaq Composite chart goes back further.
- **Projects made before the studio upgrade** still open. Their cards and asset board work;
  thumbnails and graphics that need a chart ask you to generate the project again, because
  older projects did not save each chart's plotted data.
- **Timeline exports** describe your raw recording (times come from the keys you pressed).
  The `.fcpxml` is written to the FCPXML 1.9 format; relink the media if your editor asks.
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
app.py                   start here: python app.py
vps/server.py            web API (FastAPI)
vps/pipeline.py          the Generate button, end to end
vps/catalog.py           series, charts and topic families (configuration, no numbers)
vps/topics.py            topic -> which charts
vps/sources/             FRED, BLS, Treasury, SEC EDGAR, shared HTTP layer
vps/builder.py           fetch data, draw charts, build the fact sheet
vps/facts.py             fact sentences, built by code
vps/charts.py            chart rendering (matplotlib)
vps/wording.py           built-in template wording
vps/voice.py             plain-English lines and B-roll ideas for the templates
vps/llm.py               optional LLM wording (Anthropic API or local Ollama)
vps/numbers.py           the number guard
vps/package.py           outline, shot list, titles, description
vps/compliance.py        checklist rules
vps/clips.py             transcript -> clip plan, spoken fact-check, captions
vps/projects.py          project folders and ZIP export
vps/recording_cards.py   editable cards, pinned facts, undo/redo, cue log
vps/timeline.py          YouTube chapters, .edl, .fcpxml
vps/asset_board.py       scene slots, file import, reusable library
vps/thumbnails.py        thumbnail layouts, host photos, presets, phone preview
vps/graphics.py          reveal animation, highlight, comparison card, flow diagram
vps/fact_diff.py         freeze facts, re-fetch, diff, apply choices
vps/learning_log.py      per-episode log and evidence summary
vps/transcribe.py        faster-whisper, dead-air stripping, 9:16 export
vps/media.py             ffmpeg / ffprobe helpers
web/                     the front end (plain HTML, CSS, JavaScript)
tests/
```
