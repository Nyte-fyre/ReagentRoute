"""Build data/vendor_prices.json: reagents (that actually show up in our
own recipe data) which are sold by an in-game vendor NPC for a fixed
copper price -- as opposed to needing an Auction House listing at all.

Why this matters: TSM's public pricing feed only has data for items that
someone actually listed on that realm's Auction House. Some reagents are
essentially never listed there because everyone just buys them from a
vendor for a few copper (glass Vials for Alchemy potions are the clearest
example -- see the Atiesh-Horde Alchemy investigation this was built for).
A missing AH listing for one of these isn't a real gap, it's just nobody
bothering to sell something a vendor already sells for pennies.

Verified against our own already-downloaded raw SQL dumps, not guessed:
  1. item_template.BuyPrice (the copper cost from any vendor that carries
     it) -- confirmed real column index by reading the dump's own CREATE
     TABLE statement rather than assuming a schema from memory (classic
     and tbc-db differ: tbc-db has an extra `unk0` column before `name`,
     shifting every later column index by one).
  2. Cross-checked against npc_vendor (which NPCs sell which item) to
     confirm the item is ACTUALLY vendor-sold, not just carrying a
     leftover BuyPrice value with no vendor attached.
  3. Critically: npc_vendor also has `maxcount` (0 = unlimited restock,
     nonzero = a limited number that slowly regenerates over `incrtime`
     seconds) and `condition_id` (nonzero = gated behind reputation/quest/
     other requirement). The whole point of using a vendor price as a cost
     floor is the same assumption this project already applies to vendor
     SELL price: genuinely unlimited depth at a fixed price. A first pass
     of this script naively included ANY item with a BuyPrice + a
     npc_vendor row -- and that caught real false positives: common herbs
     like Silverleaf showed up because of a vendor selling a small,
     slow-restocking supply (maxcount=3, incrtime=7200s), not the
     always-available reagent vendors this is meant to model. Only items
     with at least one npc_vendor row that is BOTH maxcount=0 AND
     condition_id=0 count as a candidate.
  4. Even after that filter, a second false-positive class showed up:
     `condition_id` doesn't capture every real-world restriction (e.g. a
     single reputation-vendor NPC can have condition_id=0 in this table
     while the reputation gate is actually enforced elsewhere). The
     giveaway is that ordinary reagent vendors (Empty Vial, Leaded Vial)
     are sold by 90+ distinct NPCs across the world, while single-special-
     vendor items (Void Crystal, Large Prismatic Shard, Fel Lotus, Hula
     Girl Doll, Elixir of Demonslaying -- verified by name: the exact
     items a "General Goods Vendor"/"Griftah"-style single NPC carries)
     have exactly 1. MIN_DISTINCT_VENDORS filters on that. A couple of
     holiday-event items (Snowball, Hula Girl Doll) are excluded by name
     regardless, since being time-of-year-limited isn't something this
     table encodes at all.

Requires raw_data/classic/ClassicDB.sql and raw_data/tbc/TBCDB.sql (run
scripts/fetch_data.py first if missing).
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from scripts.sql_dump_utils import extract_table_sql, parse_tuples, unquote  # noqa: E402

MIN_DISTINCT_VENDORS = 3

# Known holiday-event-only items -- excluded by name regardless of vendor
# count, since npc_vendor has no concept of "only sold during Winter Veil".
HOLIDAY_EXCLUDE = {"Snowball", "Hula Girl Doll"}


def to_int(field):
    field = field.strip()
    return int(field) if field.lstrip("-").isdigit() else 0


def load_vendor_buy_prices(sql_path, entry_idx, name_idx, buy_price_idx):
    """Returns {item_name: buy_price_copper} for items with a nonzero
    BuyPrice, sold unlimited/ungated (maxcount=0, condition_id=0) by at
    least MIN_DISTINCT_VENDORS distinct NPCs -- see the module docstring
    for why both filters matter."""
    text = open(sql_path, encoding="utf-8", errors="replace").read()
    item_rows = parse_tuples(extract_table_sql(text, "item_template"))
    vendor_rows = parse_tuples(extract_table_sql(text, "npc_vendor"))

    VENDOR_ENTRY_IDX, ITEM_ENTRY_IDX, MAXCOUNT_IDX, CONDITION_IDX = 0, 1, 2, 5
    vendors_by_item = {}
    for t in vendor_rows:
        if to_int(t[MAXCOUNT_IDX]) == 0 and to_int(t[CONDITION_IDX]) == 0:
            item_entry = to_int(t[ITEM_ENTRY_IDX])
            vendors_by_item.setdefault(item_entry, set()).add(to_int(t[VENDOR_ENTRY_IDX]))

    widely_available_entries = {
        item_entry for item_entry, vendors in vendors_by_item.items()
        if len(vendors) >= MIN_DISTINCT_VENDORS
    }

    out = {}
    for t in item_rows:
        entry = to_int(t[entry_idx])
        if entry not in widely_available_entries:
            continue
        buy_price = to_int(t[buy_price_idx])
        if buy_price <= 0:
            continue
        name = unquote(t[name_idx])
        if not name or name in HOLIDAY_EXCLUDE:
            continue
        # Same name can appear more than once in the dump (see the item
        # name-collision issue documented in build_gatherable_materials.py)
        # -- keep the cheapest confirmed vendor price if that happens,
        # since that's the price a rational buyer would actually pay.
        if name not in out or buy_price < out[name]:
            out[name] = buy_price
    return out


def collect_reagent_names(patterns):
    names = set()
    for pattern in patterns:
        for path in glob.glob(pattern):
            d = json.load(open(path, encoding="utf-8"))
            for r in d["recipes"]:
                for g in r.get("reagents", []):
                    names.add(g["item_name"])
    return names


def main():
    print("Loading item_template + npc_vendor from classic-db and tbc-db SQL dumps...")
    classic_prices = load_vendor_buy_prices(
        "raw_data/classic/ClassicDB.sql", entry_idx=0, name_idx=3, buy_price_idx=8
    )
    tbc_prices = load_vendor_buy_prices(
        "raw_data/tbc/TBCDB.sql", entry_idx=0, name_idx=4, buy_price_idx=9
    )
    print(f"  {len(classic_prices)} classic vendor-sold items, {len(tbc_prices)} tbc vendor-sold items.")

    # Merge, preferring the cheaper confirmed price where both dumps have
    # the same name (vendor prices for common reagents are usually static
    # across expansions, but take the lower one if they ever disagree).
    merged = dict(classic_prices)
    for name, price in tbc_prices.items():
        if name not in merged or price < merged[name]:
            merged[name] = price

    reagent_names = collect_reagent_names(["data/*_recipes.json", "data/*_tbc_recipes.json"])
    print(f"  {len(reagent_names)} unique reagent names across Classic + TBC recipe data.")

    matched = {name: merged[name] for name in reagent_names if name in merged}
    print(f"\n{len(matched)} reagents are vendor-sold at a known price:")
    for name, price in sorted(matched.items(), key=lambda kv: kv[1]):
        gold, rem = divmod(price, 10000)
        silver, copper = divmod(rem, 100)
        print(f"  {gold:3d}g {silver:2d}s {copper:2d}c  {name}")

    out_path = "data/vendor_prices.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matched, f, indent=2, sort_keys=True)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
