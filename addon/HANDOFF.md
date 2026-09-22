# Handoff: ReagentRoute companion addon

Brief for whoever (human or agent) builds the in-game WoW addon that
bridges to [ReagentRoute](https://reagentroute.onrender.com)
([GitHub](https://github.com/Nyte-fyre/ReagentRoute)). Written so you can
pick this up cold, with no other context from this project's history.

## Status

P0 (owned-materials + skill export) and P1 (shopping-list import/checklist)
both have an initial implementation in `addon/ReagentRoute/`:
- `Export.lua` -- bag scanning (owned materials by item ID) + profession
  skill reads
- `Import.lua` -- parses a pasted `itemID: quantity` shopping list
- `Core.lua` -- UI: `/rr` or `/reagentroute` opens the export panel (copy-
  able owned-materials box + read-only skill display); `/rr list` or the
  panel's "Shopping List..." button opens the checklist
- `Checklist.lua` -- paste-a-shopping-list-in, get an auto-ticking
  checklist (reads bag counts live on `BAG_UPDATE`)
- Flavor-suffixed `.toc` files for Classic Era (`_Vanilla`) and TBC
  Anniversary (`_TBC`)

**Verified live against a real TBC Anniversary client and the live site**
(2026-09-22, character on `_anniversary_`, found via `.build.info` --
`wow_anniversary` product, confirmed separate from `_classic_` and
`_classic_era_`):
- Addon loads with no "out of date" warning -- the derived Interface
  number (`20506`) was correct, not just a guess that happened to work.
- `/rr`'s Select All + Ctrl+C copies the exact `itemID: quantity` text
  (read the OS clipboard directly to confirm, not just eyeballed).
- Pasted that exact addon-exported string (`2589: 6`, later `2589: 9`)
  into the live site's owned-materials box -- `COST TO YOU` dropped by
  precisely `qty x unit_cost_copper` to the copper, both times.
- The website's shopping-list export box (`2589: 59`) pasted into `/rr
  list` resolved to the correct item name/icon and correct have/need
  counts against the same character's real bags.
- `BAG_UPDATE` auto-tick verified both directions with a real vendor
  transaction (sell 1 Linen Cloth -> checklist flipped `9/9` green to
  `8/9` red with no Rescan click; Buyback tab to repurchase -> flipped
  back to `9/9` green), so the checklist genuinely updates live, not just
  on manual refresh.

**Also verified live on Classic Era** (2026-09-22, different character, on
`_classic_era_`): addon loads cleanly, `/rr` scans real bags (30 distinct
items), Select All + Ctrl+C copies correctly (read via OS clipboard). The
Interface number is no longer just derived here -- `/dump select(4,
GetBuildInfo())` returned `11509` in-game, an exact match to what was in
`ReagentRoute_Vanilla.toc`, confirmed rather than assumed from Blizzard's
usual numbering convention. The owned-materials round trip was verified
on Classic Era too: this character genuinely owned 4x Silk Cloth (item
4306), and pasting `4306: 4` into a First Aid 1-300 plan on the live site
dropped `NET COST` from `17g 52s 93c` to `COST TO YOU` `17g 42s 93c` --
exactly `4 x 2s50c` (Silk Cloth's unit cost), to the copper.

The P1 shopping-list checklist was also verified on Classic Era: pasted
the site's real First Aid 1-300 export (`1475: 160`, `4306: 360`,
`4338: 54`, `14047: 80`, `2589: 326`) into `/rr list`, clicked Build, and
all five resolved to correct names/icons (Small Venom Sac, Linen Cloth,
Silk Cloth, Mageweave Cloth, Runecloth) with correct have/need counts --
`Silk Cloth -- 4 / 360` matched the character's real bag count exactly.
This also caught and fixed a real bug: `pasteBox` (the paste-in EditBox)
never got an explicit `SetHeight()`, so its actual clickable area was
only a sliver of the visible 60px scroll box -- most clicks fell through
to the game world underneath (observed live: keystrokes toggled
nameplates instead of typing). Fixed by setting an explicit height and
having the whole scroll area focus the box on click, not just the box's
own tiny hit region.

**Still not verified:** re-confirming `BAG_UPDATE` live-refresh
specifically on Classic Era (proven on TBC Anniversary with a real
vendor sell/buyback; same Lua code path, not re-run here) -- low risk but
genuinely untested on this client. WoW Forever is untested entirely
(addon support there is still an open question, see below).

The two website-side changes P1 needed are live and verified (see Data
contract below) -- `addon/WEBSITE_HANDOFF.md` is now historical record of
the spec, not a pending TODO.

## What ReagentRoute is

A web tool that computes the cheapest path to level a WoW Classic
profession, priced against live Auction House data. Backend is FastAPI
(`webapp/main.py`), frontend is vanilla JS/HTML/CSS (`webapp/static/`),
recipe data is static JSON per profession (`data/*_recipes.json`), and
pricing is joined at request time from TradeSkillMaster's public CSV feed
(`price_recipes.py`). It supports three game versions: Classic Era
(`classic`), TBC Anniversary (`tbc`), and WoW Forever beta (`forever`).

Read `README.md` at the repo root before starting -- it documents the
data pipeline, known limitations, and the verification standard this
project holds itself to (every fact checked against a primary source,
nothing guessed). The addon should hold itself to the same standard.

## Why an addon -- three real gaps it can close

These aren't hypothetical nice-to-haves; they're gaps the website
currently cannot close from outside the game client:

1. **No live AH pricing for TBC Anniversary or WoW Forever.** Verified
   this session: TSM's public feed only covers `classic`,
   `classic-progression`, and `retail` (tested the URL pattern directly,
   got 404s for every guessed TBC/Forever slug); Blizzard's own Game Data
   API has no namespace for either yet. An addon that scans the AH while
   the player has it open and exports the results is the most plausible
   way to get real pricing for these versions before Blizzard/TSM catch up.
2. **No acquisition data at all for WoW Forever recipes.** No community
   emulator project exists yet for a beta that launched days ago (see
   `README.md`'s Known Limitations), so there's no trainer/vendor/loot
   table to check against -- every Forever recipe is tagged `unknown`.
   An addon that reads the trainer window, vendor window, or loot text
   when a player actually encounters these in-game is the *only* way
   this gap ever closes, short of Blizzard shipping one themselves.
3. **Manual data entry friction on the website.** "Materials you already
   own" and "Start skill" currently require the player to type them in by
   hand. An addon can read both directly from the game and export a
   ready-to-paste string.

## Read this before writing any Lua

- **Addons cannot make network requests.** No exceptions, this is a hard
  client sandbox restriction. Every exchange between the addon and the
  website has to be a **copy-paste text string** through the UI: an
  `EditBox` in-game the player selects-all-and-copies, pasted into a
  textarea on the site (or vice versa). This is the same pattern TSM
  shopping lists, WeakAuras import strings, and Pawn strings already use
  -- nothing novel needed, just follow that convention.
- **Stay within Blizzard's Addon API ToS.** Read-only observation of game
  state and UI, and player-initiated UI actions only. No automating game
  actions, no simulated input, no botting-adjacent behavior. Everything
  proposed below (reading bags, trade skill lists, the AH UI, trainer/
  vendor windows) is squarely inside what addons have always been allowed
  to do.
- **Three client targets, and the third one is genuinely unknown.**
  Classic Era and TBC Anniversary both run on well-understood
  Classic-family client code. WoW Forever is a brand-new beta (this
  session confirmed via Blizzard's own forums that even the *players*
  don't know yet whether it's built on the Classic addon API or the
  Retail one -- there's an open, unanswered thread on Blizzard's forums
  asking exactly that). Concretely: the bag-scanning API differs between
  the older global functions (`GetContainerNumSlots`, `GetContainerItemLink`,
  ...) and the newer `C_Container.*` namespace, and which one a given
  client build supports has to be checked empirically once you have
  access, not assumed from this document. Same caution applies to
  `C_TradeSkillUI` vs the older `GetTradeSkillLine`-style globals for
  reading known recipes. Use `GetBuildInfo()` and the `WOW_PROJECT_ID`
  global to detect which client you're actually running on, and verify
  Forever's value for that empirically -- don't guess it.
- **Confirm addons are even enabled for Forever's beta before investing
  real time.** Not confirmed either way as of this writing.

## Data contract -- match the website's shape

**Fixed and live.** `apply_owned_materials()` in `optimize_leveling.py`
used to match owned-materials entries against each recipe reagent's
`item_name` field by exact string only, which meant a paste-in export had
to reproduce the exact in-game display name verbatim -- any mismatch
(extra whitespace, a different locale, a hyperlink-wrapped item string)
silently zeroed out credit for that item with no error shown.
`Export.lua`'s `ScanOwnedMaterials()` sidesteps this by reading item IDs
directly off bag slots via the container API (no `GetItemInfo` name-cache
wait needed) and exporting `itemID: quantity` lines instead of names.
`apply_owned_materials()` now matches each reagent's `item_id` first,
falling back to `item_name`, against one shared pool -- landed in commit
`f73635d`, live on reagentroute.onrender.com. Verified live end-to-end
(not just via the website session's own curl test): pasting an
addon-exported `itemID: quantity` string into the site's existing
`"Materials you already own"` textarea reduces `COST TO YOU` by exactly
the expected amount, to the copper. Do the ID-not-name approach for any
future export feature that adds new owned-material sources, same as
`Export.lua` already does.

### Recipe JSON shape (what the addon should assume the site knows)

One example object from `data/first_aid_recipes.json`, representative of
every profession/version file's shape:

```json
{
  "spell_id": 3275,
  "craft_spell_id": 3275,
  "spell_name": "Linen Bandage",
  "crafted_item_id": 1251,
  "crafted_item_name": "Linen Bandage",
  "required_skill_value": 1,
  "skill_tier": "Apprentice",
  "reagents": [{"item_id": 2589, "item_name": "Linen Cloth", "count": 1}],
  "auto_granted": true,
  "learned_from": {"type": "automatic"},
  "acquisition": "automatic",
  "acquisition_note": "Known automatically once you reach this skill level in the profession -- no trainer purchase or recipe item needed.",
  "source": "cmangos-classic-db+client-data-acquiremethod",
  "confidence": "verified",
  "trivial_low": 30,
  "trivial_high": 60,
  "vendor_sell_price": 20
}
```

`acquisition` values currently in use: `trainer`, `vendor`, `drop`,
`quest`, `multiple`, `unresearched` (tried to resolve, couldn't),
`automatic` (this session's addition -- known free at a skill threshold,
no trainer/item needed), and `unknown` (Forever only -- no data source
exists to check against at all). An addon-sourced acquisition report for
Forever should slot into this same enum plus a note field, not invent a
new shape.

### Live API surface (`webapp/main.py`)

- `GET /api/game-versions` -- `[{id, label, pricing_available, ...}]`
- `GET /api/professions?game_version=` -- professions + recipe counts
- `GET /api/realms?game_version=` -- curated realm list, `{realms, factions}`
- `GET /api/recipes?profession=&game_version=` -- full recipe browse (used
  for TBC/Forever, which have no pricing)
- `POST /api/plan` -- the priced-route computation. Body is `PlanRequest`:
  `{profession, game_version, start_skill, target_skill, game_type,
  region, realm, owned_materials: {itemName: qty}, gathering_professions:
  [ids], hedge_ah, ah_hedge_cap}`. Response includes the priced plan and
  a consolidated `shopping_list` (see `build_shopping_list()` in
  `optimize_leveling.py`: `[{item_id, item_name, total_count,
  unit_cost_copper, total_cost_copper, gathered, vendor_bought}]`).

Realm/faction convention for pricing: `game_type` (`classic`/`tbc`),
`region` (`us`/`eu`/...), `realm` slug, faction implied by an
`-horde`/`-alliance` suffix TSM itself uses -- see `REALMS` in
`webapp/main.py` and TSM's own public-data docs
(https://tradeskillmaster.com/public-data) for the exact slug format.

## Proposed features, in priority order

### P0 -- MVP, ships first
- **Owned-materials export.** Scan bags (+bank if open) via whatever
  container API this client build actually exposes, aggregate by exact
  item name, and format as `Item Name: quantity` per line -- literally
  the same format the site's "Materials you already own" textarea
  already accepts by hand, so zero website changes needed for this one.
- **Start-skill autofill.** Read the player's current skill value for
  the selected profession and format it for a one-click paste (or just
  display it plainly for the player to type -- this one's low-stakes
  enough that a full string protocol may be overkill).

### P1 -- shopping list round-trip (implemented and verified live)
- `Checklist.lua`/`Import.lua` accept a pasted shopping-list export and
  turn it into an in-game checklist, auto-ticking items off by reading
  current bag counts on `BAG_UPDATE`. Format chosen: `itemID: quantity`
  per line, mirroring the owned-materials export shape rather than
  `Item Name x Quantity`, for the same item-ID-over-name reasoning as the
  Data contract section above. The website now produces this text (a
  "Copy" button + read-only export box under the shopping list table,
  commit `f73635d`) -- pasting its output into `/rr list` and clicking
  Build correctly resolves names/icons and have/need counts against real
  bags, and the checklist live-updates on `BAG_UPDATE` (verified with an
  actual vendor sell + buyback, not just a Rescan click).

### P2 -- stretch, but highest strategic value
- **AH scan export for TBC/Forever.** When the player opens the AH,
  capture per-item price data and export it in (or close to) TSM's own
  public CSV shape -- `itemId, name, marketValue, minBuyout, recent,
  historical, updatedAt` -- so `price_recipes.py` needs minimal changes
  to consume a pasted/uploaded version of it as a stand-in pricing source
  for the versions TSM doesn't cover yet. This is the single highest-value
  thing this addon could do, since it's the one gap nothing else can fill.
- **Forever acquisition reporting.** When a player opens a trainer,
  vendor, or loots a recipe item in Forever specifically, capture that
  context (NPC name + window type, or loot source) and export it in a
  form that can be merged into `data/*_forever_recipes.json`'s
  `acquisition`/`acquisition_note` fields by hand or via a small script,
  the same shape `scripts/extract_profession_tbc.py`'s `describe()`
  function already produces for TBC. This is the only realistic path to
  ever resolving Forever's `unknown` acquisition tags, short of a
  community emulator project appearing.

## Repo layout (current)

The addon lives in this repo under `addon/`, alongside `webapp/`,
`scripts/`, and `data/` -- it's part of the same product, not a separate
project.

```
addon/
  ReagentRoute/
    ReagentRoute_Vanilla.toc  # Classic Era -- Interface number flagged for verification
    ReagentRoute_TBC.toc      # TBC Anniversary -- Interface number flagged for verification
    Export.lua                 # owned-materials scan + profession skill reads
    Import.lua                 # shopping-list paste-in parsing
    Checklist.lua               # shopping-list checklist UI (/rr list)
    Core.lua                   # main UI: /rr or /reagentroute panel
  HANDOFF.md                  # this file
  WEBSITE_HANDOFF.md          # spec for the two website-side changes P1 needs
```

Two separate `.toc` files (Blizzard's flavor-suffix convention -- `_Vanilla`,
`_TBC`, `_Wrath`, `_Cata`, `_Mainline`) instead of one `.toc` with multiple
comma-separated `## Interface:` values, since Classic Era and TBC
Anniversary are different enough client lines that they may eventually
need different Lua too (this addon's code happens to be identical across
both right now via runtime API detection in `Export.lua`, not TOC
branching). Each `.toc`'s Interface number is a best guess, not verified
against a live client -- see the NOTE comment inside each file for the
exact command to check it with, and update before shipping. No WoW
Forever `.toc` yet -- open question #1 below (whether Forever allows
addons at all) hasn't been answered.

No `Libs/` folder -- no embedded libraries were needed; the UI uses only
Blizzard's built-in widget templates (`BasicFrameTemplateWithInset`,
`UIPanelScrollFrameTemplate`, `UIPanelButtonTemplate`).

## Open questions to resolve empirically, not by assumption

1. Does Forever's beta allow third-party addons at all right now?
2. What's Forever's actual `WOW_PROJECT_ID` / interface version, and does
   it use the Classic-style or Retail-style container/tradeskill API?
3. UX preference for the copy-paste bridge: a plain `EditBox` the player
   manually selects, or something fancier (QR-code-style chunking for
   very long strings, a SavedVariables file the player attaches instead)?
   Start with the simplest EditBox approach and only add complexity if a
   real string-length problem shows up.
4. For the AH-scan export specifically: TSM's own scanner takes multiple
   passes to fully populate `minBuyout` for every item on a realm --
   decide whether a partial scan is worth exporting incrementally or only
   once a full pass completes.

## Definition of done for the MVP (P0)

- [x] Addon loads without error on both TBC Anniversary and Classic Era
  -- verified live 2026-09-22 on real characters on both clients, no
  "out of date" warning on either; Classic Era's Interface number (11509)
  confirmed exactly via `/dump select(4, GetBuildInfo())` in-game, not
  just inferred from a clean load. Forever still pending open question #1.
- [x] Player can open the addon's export panel (`/rr`), get a materials
  string (`item_id: quantity` per line), paste it into the site's
  existing textarea, and see it correctly reduce the plan's cost --
  verified live on both clients: TBC Anniversary (`2589: 6`, then
  `2589: 9`) and Classic Era (`4306: 4`), each reducing `COST TO YOU` by
  exactly `qty x unit_cost_copper`, to the copper, against the live site.
- [x] No network calls anywhere in the addon -- confirmed by inspection,
  `Core.lua`/`Export.lua` only touch `CreateFrame`/container/profession
  APIs and string formatting, nothing that could shell out to anything.

## Definition of done for P1 (shopping list round-trip)

- [x] Website produces a copy-able `itemID: quantity` export matching
  `ParseShoppingList()`'s expected shape -- verified live on both clients
  (`2589: 59` on TBC Anniversary, a 5-item First Aid export on Classic
  Era).
- [x] Pasting that export into `/rr list` and clicking Build resolves
  correct item names/icons and correct have/need counts against real bag
  contents -- verified on both clients.
- [x] Checklist updates live on `BAG_UPDATE` with no manual Rescan --
  verified on TBC Anniversary both directions with a real vendor sell
  (`9/9` -> `8/9`) and Buyback repurchase (`8/9` -> `9/9`). **Not
  re-verified on Classic Era** -- same Lua code path, low risk, but
  genuinely untested there.
