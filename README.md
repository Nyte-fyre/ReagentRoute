# ReagentRoute

A WoW Classic tool that computes the cheapest path to level a crafting
profession, priced against live Auction House data and personalized
against materials you already own.

Not affiliated with Blizzard Entertainment. World of Warcraft and all
game data referenced here are trademarks/copyright of Blizzard
Entertainment. This is a fan-made tool.

## What it does

Supports three game versions: **Classic Era**, **TBC Anniversary**, and
an early **WoW Forever (beta)** scaffold. The web app's game-version
selector switches between them, showing only that version's professions
and (where available) its realm list.

1. **Recipe data** -- every recipe for 7 professions (8 in TBC, adding
   Jewelcrafting), with verified reagent lists, real skill-up thresholds,
   and how each one is actually acquired (trainer, vendor, drop, quest).
   WoW Forever has its own extraction pipeline covering all 8 professions
   it currently has (no Jewelcrafting in this build) -- see
   [Known limitations](#known-limitations) for what's still missing
   (acquisition data, trainer-only recipes with no representative item).
2. **Live pricing** -- joins recipes against real-time Auction House data
   (Classic Era only right now -- see [Known limitations](#known-limitations)).
3. **Cost optimization** -- an expected-value solver picks the cheapest
   recipe at every single skill point, accounting for the real
   Orange/Yellow/Green/Grey skill-up probabilities (not the "flat 100%
   until grey" approximation most calculators use).
4. **Net cost, not gross** -- nets out guaranteed vendor resale value of
   what you craft along the way.
5. **Personalization** -- give it a list of materials you already own and
   it recomputes what the path actually costs *you*.

Try it: run the web app (see [Setup](#setup)) and pick a profession,
realm, and skill range.

## How the numbers are verified

This project leans hard on "don't trust it, check it" -- most of the
interesting engineering here was chasing down and fixing wrong data
before it went into the model, not just wiring APIs together. A few
examples (see git history / commit messages for the full story):

- **Skill-up probabilities**: Blizzard never published the real formula,
  and community folklore ("linear interpolation across Yellow/Green") is
  wrong. The actual model (flat 100% / 75% / 25% / 0% per color band) was
  pulled from the [cmangos](https://github.com/cmangos) emulator
  projects' production server code, which has been continuously refined
  against real client behavior for 15+ years.
- **Auction House hedging**: crafted items get vendor-sold back, but only
  vendor price is used in the cost model. An earlier version also
  subtracted Auction House price and produced "expect to profit 50,000g
  leveling this profession" -- obvious nonsense. The bug: applying a
  single live AH listing's price as if you could sell unlimited
  duplicates at it, when in reality flooding the market crashes the
  price. AH value is now surfaced per-item as an FYI, never multiplied
  into the total.
- **TBC data**: `tbc-db`'s own `item_template.spellid_1` field turned out
  to be broken (the same placeholder value on every single row, verified
  across dozens of items) -- replaced with the correct `ItemEffect` DB2
  table pulled from the actual game client.
- **Forever data**: same `spellid_1`-is-broken issue, plus this build
  splits the item-teaches-spell relationship into its own join table
  (`ItemXItemEffect`) instead of a flat column -- and many schematic
  items simply have no `RequiredSkillRank` populated yet (beta), which
  would otherwise silently mislabel high-tier recipes as available at
  skill 1. Falls back to the recipe's own verified Orange/Yellow/Green/Grey
  threshold (`TrivialSkillLineRankLow`) instead of trusting a missing field.

## Project structure

```
data/                   Extracted recipe datasets (the actual deliverable)
  *_recipes.json          Classic Era, one file per profession
  *_tbc_recipes.json      TBC Anniversary, one file per profession
  *_forever_recipes.json  WoW Forever (beta), one file per profession
  SkillLineAbility_*.csv  Real skill-up thresholds per game version

scripts/                Data extraction pipeline
  fetch_data.py              Downloads raw SQL dumps / DB2 CSVs into raw_data/ (Classic + TBC)
  fetch_data_forever.py      Downloads DB2 CSVs into raw_data/forever/ (WoW Forever)
  sql_dump_utils.py          Shared SQL-dump parsing (no DB server needed)
  extract_profession.py      Classic Era: one profession -> data/*.json
  extract_profession_tbc.py  TBC Anniversary: one profession -> data/*.json
  extract_profession_forever.py  WoW Forever: one profession -> data/*.json
  backfill_sell_price.py     Adds vendor sell price to Classic Era recipes

price_recipes.py        Joins recipes against live TSM pricing data
optimize_leveling.py    The expected-value cost optimizer
webapp/                 FastAPI backend + vanilla JS/HTML/CSS frontend
test_connection.py      Verifies your Blizzard API credentials work
legacy/                 Superseded single-profession scripts (see legacy/README.md)
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your Blizzard API credentials (optional, see below)
python scripts/fetch_data.py   # downloads ~200MB of raw SQL/CSV data
python scripts/extract_profession.py Engineering 202 3   # extract one profession
python -m uvicorn webapp.main:app --reload   # start the web app at localhost:8000
```

`.env` / Blizzard API credentials are only used by `test_connection.py`
(a sanity check that your API setup works) -- the actual recipe
extraction pipeline doesn't call Blizzard's API at all, because it
doesn't expose profession/recipe data for Classic (see below). Get free
credentials at the [Blizzard Developer Portal](https://develop.battle.net/access/clients)
if you want to run that check.

### Extracting all professions

```bash
# Classic Era
python scripts/extract_profession.py Engineering 202 3
python scripts/extract_profession.py Blacksmithing 164 4
python scripts/extract_profession.py Alchemy 171 6
python scripts/extract_profession.py Leatherworking 165 1
python scripts/extract_profession.py Tailoring 197 2
python scripts/extract_profession.py Cooking 185 5
python scripts/extract_profession.py Enchanting 333 8
python scripts/backfill_sell_price.py   # adds vendor sell price to all of the above

# TBC Anniversary (adds Jewelcrafting; skill line ids are the same for carried-over professions)
python scripts/extract_profession_tbc.py Engineering 202 3
python scripts/extract_profession_tbc.py Blacksmithing 164 4
python scripts/extract_profession_tbc.py Alchemy 171 6
python scripts/extract_profession_tbc.py Leatherworking 165 1
python scripts/extract_profession_tbc.py Tailoring 197 2
python scripts/extract_profession_tbc.py Cooking 185 5
python scripts/extract_profession_tbc.py Enchanting 333 8
python scripts/extract_profession_tbc.py Jewelcrafting 755 10

# WoW Forever (beta) -- no trainer table exists yet (see Known limitations),
# so only recipes with a physical schematic/pattern/formula item are found.
# No Jewelcrafting item subclass exists in this build.
python scripts/fetch_data_forever.py
python scripts/extract_profession_forever.py Engineering 202 3
python scripts/extract_profession_forever.py Blacksmithing 164 4
python scripts/extract_profession_forever.py Leatherworking 165 1
python scripts/extract_profession_forever.py Alchemy 171 6
python scripts/extract_profession_forever.py Cooking 185 5
python scripts/extract_profession_forever.py Tailoring 197 2
python scripts/extract_profession_forever.py Enchanting 333 8
python scripts/extract_profession_forever.py "First Aid" 129 7
```

Current dataset: **1,204 Classic Era recipes** + **1,888 TBC Anniversary
recipes** across 7-8 professions each, plus **2,005 WoW Forever recipes**
across all 8 professions this build has (no Jewelcrafting).

### Realm pricing

Pricing comes from [TradeSkillMaster's public data](https://tradeskillmaster.com/public-data)
-- free, static CSVs, no API key or rate limit. The web app's Realm
dropdown lists a curated, TSM-verified sample per game version (currently
Classic Era only, since that's the only version with pricing); pass any
other realm slug + `-horde`/`-alliance` straight to `price_recipes.py`
directly if yours isn't listed yet. Find a realm's exact slug by opening
it at tradeskillmaster.com and copying it from the address bar.

## Known limitations

- **No live pricing for TBC Anniversary.** Neither Blizzard's own Game
  Data API nor TSM's public pricing data distinguishes the new
  Anniversary/TBC realm line (launched Nov 2024, reached TBC content
  Feb 2026) from other realm lines -- Blizzard's API has no matching
  namespace at all, and TSM's `classic-progression` bucket turns out to
  be the *original* 2019 progression line, which has already advanced
  past TBC into WotLK (confirmed: Death Knight glyphs, a WotLK-only
  class, show up in that data). The web app falls back to a recipe
  browser (no cost optimization) for TBC until a pricing source surfaces.
- **Acquisition data for some non-trainer recipes is unresearched.**
  Drop/vendor/quest resolution chases direct loot tables, shared
  reference loot pools, item containers, and fishing pools, but a
  handful of recipes per profession (mostly rare/seasonal items) aren't
  captured by any of those and are honestly tagged `unresearched` rather
  than guessed.
- **AH price estimates don't model the in-game cut/deposit.** The
  informational per-unit AH value shown next to some items is the
  current cheapest live listing, gross of Blizzard's auction cut.
- **Skill-up percentages are a verified model, not a guarantee.**
  Sourced from production emulator code refined against real client
  behavior for 15+ years, but it's still a model of Blizzard's
  unpublished formula, not the formula itself.
- **WoW Forever's recipe data covers all 8 of its professions but is
  still incomplete within each one.** No community emulator database
  (cmangos-style) exists yet for a beta launched within the last few
  weeks, so: (1) acquisition is tagged `unknown` for every recipe --
  there's no trainer/vendor/loot/quest source to check against; (2)
  recipe discovery only finds recipes with a physical teaching item
  (Schematic/Pattern/Formula/Blueprint) -- pure trainer-only recipes
  with no representative item (common for early-tier basics) are
  invisible to this method and are missing from the dataset entirely;
  (3) beta item IDs and stats can change before Forever's full release,
  so re-extract periodically rather than treating this as stable; (4) no
  Jewelcrafting item subclass exists in this build, matching community
  guides that don't list it among Forever's professions.

## Data sources & attribution

- **Recipe/reagent/loot/vendor/quest data**: [cmangos/classic-db](https://github.com/cmangos/classic-db)
  and [cmangos/tbc-db](https://github.com/cmangos/tbc-db), GPL-3.0
  licensed content databases for the mangos-classic and mangos-tbc
  emulator projects. `raw_data/` (gitignored) holds these; run
  `scripts/fetch_data.py` to pull them fresh.
- **Skill-up thresholds, spell reagents/effects, item-teaches-spell
  links**: [wago.tools](https://wago.tools), DB2 exports of the actual
  live game client for specific builds (pinned in `scripts/fetch_data.py`
  and `scripts/fetch_data_forever.py` for reproducibility). For WoW
  Forever, wago.tools is the *only* data source (no cmangos-style
  emulator database exists for it yet) -- see Known limitations.
- **Skill-up percentage model**: derived from [cmangos/mangos-classic](https://github.com/cmangos/mangos-classic)
  server source code (`src/game/Entities/Player.cpp`).
- **Auction House pricing**: [TradeSkillMaster](https://tradeskillmaster.com/public-data)
  public data feed.
- **Item/recipe lookup links**: [Wowhead](https://www.wowhead.com).

### License

No license has been chosen for this project's own code yet. Note that
the extracted data in `data/*.json` is *derived from* cmangos'
GPL-3.0-licensed content databases -- if you redistribute those files (or
a tool built on them), check GPL-3.0's terms before assuming you can
relicense them freely.
