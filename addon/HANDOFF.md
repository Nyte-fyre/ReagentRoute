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

**Not yet tested in-game** -- no live client access when this was written,
so treat it as a first pass: verify it loads, verify the Interface numbers
in both `.toc` files (flagged inline in each with what to check), and
verify the owned-materials export round-trips into the website correctly
before calling P0 done (see its Definition of done below).

**The shopping-list checklist (P1) needs two things from the website side
that don't exist yet**, both specced in `addon/WEBSITE_HANDOFF.md`: (1)
`apply_owned_materials()` needs to match by `item_id` (currently
name-only, see Data contract below), and (2) the site needs a
`itemID: quantity` shopping-list export box for the player to copy from --
today the shopping list only renders as an HTML table, nothing
copy-pasteable. Until both land, the checklist works once pasted (parsing
is addon-side and independent), but there's nothing on the website yet to
paste *from*.

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

**Still open, patch written but not applied here.** `apply_owned_materials()`
in `optimize_leveling.py` matches owned-materials entries against each
recipe reagent's `item_name` field by exact string only, which means a
paste-in export has to reproduce the exact in-game display name verbatim
-- any mismatch (extra whitespace, a different locale, a hyperlink-wrapped
item string) silently zeroes out credit for that item with no error
shown. `Export.lua`'s `ScanOwnedMaterials()` sidesteps this by reading
item IDs directly off bag slots via the container API (no `GetItemInfo`
name-cache wait needed) and exporting `itemID: quantity` lines instead of
names. The website's `"Materials you already own"` textarea and its
`parseOwnedMaterials()` parser (`webapp/static/app.js`) already accept
that shape with zero changes -- but until `apply_owned_materials()` is
patched to also match by `item_id`, those addon-exported lines parse in
fine and silently apply **zero savings**, same failure mode as a name
mismatch always had. The exact patch (verified in isolation, not part of
this repo) is in `addon/WEBSITE_HANDOFF.md` -- this was deliberately kept
out of `optimize_leveling.py` itself since this session was scoped to the
addon, not the website; whoever owns that file should apply it through
their own process. Do the ID-not-name approach for any future export
feature that adds new owned-material sources, same as `Export.lua`
already does.

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

### P1 -- shopping list round-trip (implemented, blocked on website export)
- `Checklist.lua`/`Import.lua` accept a pasted shopping-list export and
  turn it into an in-game checklist, auto-ticking items off by reading
  current bag counts on `BAG_UPDATE`. Format chosen: `itemID: quantity`
  per line, mirroring the owned-materials export shape rather than
  `Item Name x Quantity`, for the same item-ID-over-name reasoning as the
  Data contract section above. The website doesn't produce this text yet
  (`build_shopping_list()` has the right fields, there's just no
  copy-able export in the UI) -- see `addon/WEBSITE_HANDOFF.md`.

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

- [ ] Addon loads without error on at least Classic Era and TBC Anniversary
  (Forever pending answer to open question #1). **Not yet verified --
  needs a real client.**
- [ ] Player can open the addon's export panel (`/rr`), get a materials
  string (now `item_id: quantity` per line, not `Item Name: quantity` --
  see Data contract above for why that changed), paste it into the site's
  existing textarea, and see it correctly reduce the plan's cost --
  verified with a real in-game test, not just eyeballing the string
  format. **Not yet verified.**
- [x] No network calls anywhere in the addon -- confirmed by inspection,
  `Core.lua`/`Export.lua` only touch `CreateFrame`/container/profession
  APIs and string formatting, nothing that could shell out to anything.
