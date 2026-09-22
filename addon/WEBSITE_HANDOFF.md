# Handoff: website changes needed for the companion addon

Written by the session working on `addon/ReagentRoute/` (see
`addon/HANDOFF.md` for its full brief) for whoever owns `webapp/` and
`optimize_leveling.py`. This session was scoped to the addon only and was
not directed to make website changes, so nothing here has been applied to
`optimize_leveling.py` or `webapp/` -- it's proposed, verified in
isolation, and ready to redo through your own process. Each numbered
section is independent and can land on its own.

**Sections 1 and 2 already landed** (commit `f73635d`) -- kept below as
historical record of the spec, not pending work. **Section 3 is new and
not started on the website side** -- the addon half (scanning + CSV
export) is implemented and verified live; nothing server/frontend-side
exists yet to consume it.

## 1. Match owned-materials by item ID, not just name

**Where:** `apply_owned_materials()` in `optimize_leveling.py` (currently
lines ~153-168).

**Problem:** it matches each recipe reagent's `item_name` field against
`owned_items` by exact string only. Any whitespace, locale, or
hyperlink-wrapped-string mismatch silently zeroes out credit for that item
with no error shown -- this was already flagged as a known fragility in
`addon/HANDOFF.md`'s Data contract section before any addon code existed.

**Why it matters now:** `addon/ReagentRoute/Export.lua`'s
`ScanOwnedMaterials()` reads item IDs directly off bag slots (no name
lookup needed, no async item-cache wait) and exports `itemID: quantity`
lines. Today those lines paste into the site's existing
`"Materials you already own"` textarea without error, but silently apply
**zero** savings, because the backend only ever checks `item_name`. This
patch is what actually makes that payoff real.

**Proposed patch** (replace the existing function body):

```python
def apply_owned_materials(plan, owned_items):
    """Walk the plan in order, depleting a shared owned-materials pool as
    each step's *expected* reagent consumption is subtracted from it.
    Returns (total_value_saved_copper, remaining_stock).

    `owned_items` keys may be either a reagent's exact item_name (what the
    website's free-text textarea produces, for a human typing "Copper Bar:
    40") or its numeric item_id (what the companion addon exports instead,
    since it reads item IDs directly off the client and doesn't have to
    match a display string byte-for-byte). Both key styles are matched
    against the same shared pool so a paste from either source works, and
    a single reagent's demand is only ever covered once even if the pool
    happens to have entries under both its id and its name."""
    stock = {}
    for key, qty in owned_items.items():
        norm_key = int(key) if isinstance(key, str) and key.isdigit() else key
        stock[norm_key] = qty
    total_saved = 0.0
    for skill, recipe, expected_crafts, net_ev, gross_ev in plan:
        for g in recipe["reagents"]:
            remaining = expected_crafts * g["count"]
            for key in (g["item_id"], g["item_name"]):
                if remaining <= 0:
                    break
                have = stock.get(key, 0)
                if have <= 0:
                    continue
                covered = min(have, remaining)
                stock[key] = have - covered
                total_saved += covered * g["unit_cost_copper"]
                remaining -= covered
    return total_saved, stock
```

**No frontend change needed for this half.** `parseOwnedMaterials()` in
`webapp/static/app.js` (~line 129) already splits each line on its last
`:` and takes whatever's on the left as the key verbatim -- it doesn't
care whether that's a name or a numeric ID, so `2589: 40` already parses
into `owned_materials["2589"]` today. `PlanRequest.owned_materials` in
`webapp/main.py` (~line 136) is typed `dict[str, float]`, which is also
already fine -- JSON object keys are always strings, and the patch above
normalizes any all-digit string key to `int` before matching, so a JSON
body of `{"2589": 40}` round-trips correctly.

**Verified in isolation** (not committed, this was run against the patch
above before it was reverted from this repo):

```python
from optimize_leveling import apply_owned_materials

plan = [
    (10, {'reagents': [{'item_id': 2589, 'item_name': 'Linen Cloth', 'count': 2, 'unit_cost_copper': 100}]}, 3.0, 0, 0),
    (11, {'reagents': [{'item_id': 2592, 'item_name': 'Wool Cloth', 'count': 1, 'unit_cost_copper': 200}]}, 2.0, 0, 0),
]
# Mixed: one owned by item_id (addon-style), one by name (human-typed)
owned = {'2589': 4, 'Wool Cloth': 1}
saved, remaining = apply_owned_materials(plan, owned)
assert saved == 4 * 100 + 1 * 200  # 600.0
```
Passed. No double-counting when a pool entry could theoretically match
both a reagent's id and name in the same craft (it can't in practice since
those are two different dict keys pointing at the same physical item, but
the `remaining -= covered` / early-break logic guards it structurally
regardless).

**Regression risk:** low. Existing name-keyed callers (the website's own
textarea, `owned_materials.example.json`, any other integration typing
names) are unaffected -- name matching is still the fallback and behaves
identically to before. The only behavior change is that item-ID keys now
*also* match, where before they silently matched nothing.

## 2. Add a shopping-list copy/export box

**Where:** `webapp/static/index.html` (~line 181, the
`#shopping-list-table` section) and `webapp/static/app.js`'s
`renderShoppingList()` (~line 389).

**Why:** `addon/ReagentRoute/Checklist.lua` (P1, shipped this session) lets
a player paste a shopping list into the addon and get an in-game checklist
that auto-ticks items off as they're acquired, reading current bag counts
on `BAG_UPDATE`. It expects `itemID: quantity` lines -- the same shape as
the owned-materials export, parsed by
`addon/ReagentRoute/Import.lua`'s `ParseShoppingList()`. There's currently
no way to get that text out of the website; the shopping list only
renders as an HTML table.

**Proposed shape:** one line per `build_shopping_list()` entry
(`optimize_leveling.py` ~line 274), `item_id: total_count`, e.g.:
```
2589: 40
2592: 12
3466: 6
```
`item_id` and `total_count` are already exactly the fields
`build_shopping_list()` returns per entry -- `total_count` is already a
rounded-up integer (see its docstring), so no formatting work needed
beyond `f"{e['item_id']}: {e['total_count']}"` per row.

**Suggested implementation:** a small read-only `<textarea>` (or a
"Copy shopping list" button using the Clipboard API) near
`#shopping-list-table`, populated in `renderShoppingList()` alongside the
existing table body render -- e.g.:
```js
function renderShoppingList(list) {
  const tbody = document.querySelector("#shopping-list-table tbody");
  tbody.innerHTML = list.map(...).join("");
  const exportBox = document.getElementById("shopping-list-export"); // new element
  if (exportBox) exportBox.value = list.map((e) => `${e.item_id}: ${e.total_count}`).join("\n");
}
```
Exact placement/styling is your call -- flagging the data shape and the
addon-side contract, not prescribing the UI.

## 3. Consume an addon-exported AH scan for TBC/Forever pricing

**Where:** `price_recipes.py` (new function alongside `fetch_realm_prices()`)
and `webapp/main.py`'s `PlanRequest`/`compute_plan()` (~lines 128-265),
plus frontend UI for TBC/Forever's currently browse-only path.

**Why:** README.md's Known Limitations and this repo's own `pricing_available`
flag (`webapp/main.py` ~line 55) say plainly that no pricing source exists
for TBC Anniversary -- TSM's feed doesn't cover it, Blizzard's API has no
namespace for it. `addon/ReagentRoute/AHScan.lua` closes that gap from
inside the game: it passively records buyout prices whenever the player
searches the in-game AH (never triggers searches itself -- read-only,
player-initiated, see `addon/HANDOFF.md`'s ToS section) and exports a CSV
via `RR.FormatAHScanCSV()` (`/rr ah`, "AH Scan..." button). **Verified
live** against a real Classic Era AH: searched "Linen Cloth" (two real
listings, stacks of 8 and 12), got `2589,"Linen Cloth",5416,5416` --
hand-verified against both listings' actual gold/silver/copper buyout
values divided by stack size. Not yet re-verified on TBC Anniversary
specifically, but expected to work identically (same legacy AH API,
confirmed via `/dump C_AuctionHouse, QueryAuctionItems, GetAuctionItemInfo`
returning nil/function/function on Classic Era).

**Exact CSV shape** (verified against `fetch_realm_prices()`'s own
parsing before building the export, so it's not guessed at the addon
side either):
```
itemId,name,marketValue,minBuyout
2589,"Linen Cloth",5416,5416
4306,"Silk Cloth",8900,8900
```
Only these 4 columns -- `fetch_realm_prices()` (`price_recipes.py` ~line
33) never reads `recent`/`historical`/`updatedAt` even though TSM's own
feed has them, so the addon doesn't invent those either. `marketValue` is
set equal to `minBuyout` in the export -- the addon has no way to produce
an honest smoothed estimate from a handful of live snapshots, and
`price_recipes_data()` already treats `marketValue` as informational only
(never used for the actual cost basis, see its own comments ~line 114),
so this is a safe simplification, not a shortcut that affects pricing
correctness.

**Proposed backend change:**
```python
def load_prices_from_csv_text(text):
    """Same shape/return value as fetch_realm_prices(), but parses CSV
    text directly instead of fetching from TSM -- for the addon's AH-scan
    export (see addon/WEBSITE_HANDOFF.md section 3), which is the only
    pricing source that exists for game versions TSM doesn't cover."""
    prices = {}
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        prices[int(row["itemId"])] = {
            "name": row["name"],
            "marketValue": int(row["marketValue"] or 0),
            "minBuyout": int(row["minBuyout"] or 0),
        }
    return prices
```
This is a near-identical extraction from `fetch_realm_prices()`'s existing
loop body (~lines 30-37) -- consider factoring both to share it rather
than duplicating the row-parsing logic.

In `webapp/main.py`, `PlanRequest` needs a new optional field (e.g.
`ah_scan_csv: str | None = None`), and `compute_plan()`'s pricing-source
check (~line 225, currently `if not v["pricing_available"]: raise
HTTPException(409, ...)`) needs to accept an addon-supplied scan as an
alternative to `pricing_available`: when `ah_scan_csv` is provided,
call `load_prices_from_csv_text(req.ah_scan_csv)` instead of
`fetch_realm_prices(...)`, regardless of that game version's
`pricing_available` flag. `pricing_available` itself should probably stay
`False` for TBC/Forever (it's still true that *TSM* doesn't cover them --
this is a per-request opt-in, not a change to what's available by
default).

**Frontend:** TBC/Forever currently render the browse-only fallback
(`renderBrowseResults()`, no cost optimization -- see README's Known
Limitations). Needs a paste box for the addon's CSV export, gated to
those game versions, that sends `ah_scan_csv` in the `/api/plan` request
body instead of (or in addition to) hitting the normal cost-optimized
path. Exact UX is your call -- possibilities: a textarea shown only when
`game_version` lacks `pricing_available`, with copy pasted from the
addon's window; or a small "Paste AH scan" link next to the existing
browse-only notice. Whatever shape, the data flowing in is exactly the
CSV above, unmodified.

**Not addressed here, left to you:** whether a partial scan (the player
hasn't searched every reagent yet) should compute a partial plan with
gaps flagged, or refuse until reagents are fully covered -- `optimize()`
already produces `gaps` for skill points with no priced recipe available,
which may already be the right mechanism to surface "reagent X has no
scanned price yet" without new plumbing. Worth checking before building
new gap-handling logic.

## Summary of what NOT to redo

Sections 1 and 2 already landed (`f73635d`) -- don't redo those, this doc
just keeps them as the historical spec. Section 3 (AH scan consumption)
is entirely unimplemented on the website side -- the addon's half is
done and verified live, this doc is the full spec for what's left.
