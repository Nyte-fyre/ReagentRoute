# Handoff: ReagentRoute companion addon

Brief for whoever (human or agent) builds the in-game WoW addon that
bridges to [ReagentRoute](https://reagentroute.onrender.com)
([GitHub](https://github.com/Nyte-fyre/ReagentRoute)). Written so you can
pick this up cold, with no other context from this project's history.

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

The site's item-name-based matching is a real fragility worth knowing
up front: `apply_owned_materials()` in `optimize_leveling.py` matches
owned-materials entries against each recipe reagent's `item_name` field
by **exact string**, not by item ID, even though item IDs are already
present in the data (`g["item_id"]`) and trivially available in-game via
`GetItemInfo(itemID)`. This means a paste-in export must reproduce the
exact in-game display name verbatim (which `GetItemInfo` already gives
you, so this isn't hard) -- but it also means any mismatch (extra
whitespace, a different locale, a hyperlink-wrapped item string) silently
zeroes out credit for that item with no error shown. If you're in a
position to also touch the website side, switching this match to item ID
would remove that fragility entirely; flagging it here rather than
quietly working around it in the addon.

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

### P1 -- shopping list round-trip
- Accept a pasted shopping-list export from the site (format TBD -- keep
  it simple, e.g. one `Item Name x Quantity` per line, mirroring what
  `build_shopping_list()` already returns) and turn it into an in-game
  checklist the player can tick off, ideally reading current bag counts
  to auto-check items already acquired.

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

## Suggested repo layout

Keep the addon in this repo under `addon/`, alongside `webapp/`,
`scripts/`, and `data/` -- it's part of the same product, not a separate
project. A typical WoW addon layout:

```
addon/
  ReagentRoute/
    ReagentRoute.toc      # multiple Interface: lines, one per client version
    Core.lua
    Export.lua             # owned-materials / skill / AH-scan export
    Import.lua              # shopping-list paste-in
    Libs/                   # any embedded libraries (e.g. LibDataBroker, AceAddon)
  HANDOFF.md               # this file
```

The `.toc` needs an `## Interface:` line matching each client build
you're targeting (Classic Era, TBC Anniversary, and whatever Forever's
turns out to be -- unconfirmed, verify with `/dump select(4,
GetBuildInfo())` in-game on that client).

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

- Addon loads without error on at least Classic Era and TBC Anniversary
  (Forever pending answer to open question #1).
- Player can open the addon's export panel, get a materials string in the
  exact `Item Name: quantity` format, paste it into the site's existing
  textarea, and see it correctly reduce the plan's cost -- verified with
  a real in-game test, not just eyeballing the string format.
- No network calls anywhere in the addon (grep the codebase for any HTTP
  library usage before calling this done -- there shouldn't be any way to
  even attempt one, since the WoW API doesn't expose one, but confirm no
  one tried to shell out to something exotic).
