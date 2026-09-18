"""Build data/gatherable_materials.json: which reagents that actually show
up in our own recipe data are raw materials gathered via Herbalism, Mining,
or Skinning (as opposed to bought/crafted/looted from mobs).

Classification is by the item's real Blizzard item class/subclass, read
from the same raw SQL dumps / DB2 CSVs the recipe extractors already use --
not guessed from memory. Trade Goods (class=7) subclasses are a stable
Blizzard convention across expansions:
  5 Cloth, 6 Leather, 7 Metal & Stone, 8 Meat, 9 Herb, 10 Elemental.

  - Herb (9)            -> Herbalism. Unambiguous: no other source in
                           Classic/TBC produces subclass-9 items.
  - Leather (6)          -> Skinning. Unambiguous: Leatherworking has no
                           "tan hide into leather" recipes in this era --
                           all Leather-subclass items come directly off
                           Skinning.
  - Metal & Stone (7)    -> Mining, but ONLY the raw ore/stone, not bars.
                           This subclass covers both (e.g. Copper Ore AND
                           Copper Bar), so bars/ingots are excluded by name
                           pattern -- they require a separate smelt step.
Cloth, Meat, and Elemental are deliberately left unmapped: cloth is looted
from humanoids (not a gathering profession you "have"), meat mostly drops
from any beast kill, and Elemental essences drop from elemental mobs --
none of these map to a single profession checkbox the way herbs/ore/leather do.

Requires raw_data/classic/ClassicDB.sql and raw_data/tbc/TBCDB.sql (run
scripts/fetch_data.py first if missing).
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from scripts.sql_dump_utils import extract_table_sql, parse_tuples, unquote  # noqa: E402

TRADE_GOODS_CLASS = 7
SUBCLASS_HERB = 9
SUBCLASS_LEATHER = 6
SUBCLASS_METAL_STONE = 7

BAR_PATTERN = re.compile(r"\b(Bar|Ingot)\b", re.IGNORECASE)

# Item subclass alone isn't a perfect acquisition signal -- it's an
# inventory-sorting category, not a "how do you get this" field. These
# names pass the subclass filter but are known (or reasonably suspected)
# to NOT be a raw gather, verified either against our own crafted-output
# data (they're a recipe's OUTPUT elsewhere in our dataset, i.e. a crafted
# intermediate -- see the crafted_elsewhere check below) or by specific
# outside knowledge where the automated check can't catch it:
#   - Elemental Flux, Hardened Khorium: Blacksmithing-crafted refined
#     reagents. Not caught by the crafted-output check because the
#     recipes that produce them aren't cleanly resolved in our own
#     Blacksmithing dataset, but they're not raw finds.
#   - Deeprock Salt / Refined Deeprock Salt: filed under item subclass 6
#     (Leather) in the client data for whatever internal sorting reason,
#     but there's no good evidence this is a Skinning product rather than
#     a mining-node/vendor item -- excluded pending verification rather
#     than guessed.
#   - Core Leather: not caught by the crafted-output check for the same
#     reason as Elemental Flux, but is a crafted Leatherworking reagent,
#     not a raw Skinning drop.
MANUAL_EXCLUDE = {
    "Elemental Flux", "Hardened Khorium", "Deeprock Salt",
    "Refined Deeprock Salt", "Core Leather",
}

# The inverse case: these DO show up as some recipe's crafted output (so
# the crafted-output check below would otherwise exclude them), but that
# recipe is an optional *upgrade* path (e.g. Leatherworking can turn Light
# Leather into Medium Leather), not the only source -- skinning a
# sufficiently high-level creature drops these tiers directly. Keep them
# in the gatherable set despite also being a recipe output elsewhere.
KNOWN_RAW_DESPITE_CRAFTED_ELSEWHERE = {
    "Medium Leather", "Heavy Leather", "Thick Leather", "Rugged Leather",
    "Heavy Knothide Leather",
}


def to_int(field):
    field = field.strip()
    return int(field) if field.lstrip("-").isdigit() else 0


def load_item_class_subclass_from_sql(sql_path, entry_idx, class_idx, subclass_idx, name_idx):
    """Returns {item_name: (class, subclass)} from an item_template dump."""
    text = open(sql_path, encoding="utf-8", errors="replace").read()
    values_blob = extract_table_sql(text, "item_template")
    rows = parse_tuples(values_blob)
    out = {}
    for t in rows:
        name = unquote(t[name_idx])
        if name:
            out[name] = (to_int(t[class_idx]), to_int(t[subclass_idx]))
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


def collect_crafted_names(patterns):
    """Item names that are themselves the CRAFTED OUTPUT of some recipe in
    our own data -- strong direct evidence they're a crafted intermediate,
    not a raw gather, regardless of what subclass they happen to carry."""
    names = set()
    for pattern in patterns:
        for path in glob.glob(pattern):
            d = json.load(open(path, encoding="utf-8"))
            for r in d["recipes"]:
                if r.get("crafted_item_name"):
                    names.add(r["crafted_item_name"])
    return names


def classify(item_lookup, reagent_names, crafted_elsewhere):
    herbalism, mining, skinning = set(), set(), set()
    unmapped_trade_goods = set()
    excluded_crafted, excluded_manual = set(), set()
    for name in reagent_names:
        cs = item_lookup.get(name)
        if cs is None:
            continue
        cls, subclass = cs
        if cls != TRADE_GOODS_CLASS:
            continue
        if name in MANUAL_EXCLUDE:
            excluded_manual.add(name)
            continue
        if name in crafted_elsewhere and name not in KNOWN_RAW_DESPITE_CRAFTED_ELSEWHERE:
            excluded_crafted.add(name)
            continue
        if subclass == SUBCLASS_HERB:
            herbalism.add(name)
        elif subclass == SUBCLASS_LEATHER:
            skinning.add(name)
        elif subclass == SUBCLASS_METAL_STONE:
            if BAR_PATTERN.search(name):
                continue  # smelted, not raw-gathered
            mining.add(name)
        else:
            unmapped_trade_goods.add(name)
    return herbalism, mining, skinning, unmapped_trade_goods, excluded_crafted, excluded_manual


def main():
    print("Loading item_template from classic-db and tbc-db SQL dumps...")
    classic_items = load_item_class_subclass_from_sql(
        "raw_data/classic/ClassicDB.sql", entry_idx=0, class_idx=1, subclass_idx=2, name_idx=3
    )
    tbc_items = load_item_class_subclass_from_sql(
        "raw_data/tbc/TBCDB.sql", entry_idx=0, class_idx=1, subclass_idx=2, name_idx=4
    )
    # tbc-db is additive over classic-db for shared low-level items in some
    # dumps and not others -- merge with classic as the base so a name found
    # in either dump resolves.
    merged = {**classic_items, **tbc_items}
    print(f"  {len(classic_items)} classic items, {len(tbc_items)} tbc items, {len(merged)} merged.")

    patterns = ["data/*_recipes.json", "data/*_tbc_recipes.json"]
    reagent_names = collect_reagent_names(patterns)
    print(f"  {len(reagent_names)} unique reagent names across Classic + TBC recipe data.")

    crafted_elsewhere = collect_crafted_names(patterns)

    herbalism, mining, skinning, unmapped, excl_crafted, excl_manual = classify(
        merged, reagent_names, crafted_elsewhere
    )

    print(f"\nHerbalism: {len(herbalism)} items")
    print(f"Mining:    {len(mining)} items")
    print(f"Skinning:  {len(skinning)} items")
    print(f"\nExcluded -- crafted intermediate elsewhere in our own data ({len(excl_crafted)}): {sorted(excl_crafted)}")
    print(f"Excluded -- manual review ({len(excl_manual)}): {sorted(excl_manual)}")
    print(f"\n{len(unmapped)} other Trade Goods reagents left unmapped (Cloth/Meat/Elemental/etc), not printed individually.")

    not_found = reagent_names - set(merged.keys())
    print(f"\n{len(not_found)} reagent names not found in item_template at all (likely non-item spell-only reagents or naming mismatches).")

    out = {
        "herbalism": sorted(herbalism),
        "mining": sorted(mining),
        "skinning": sorted(skinning),
    }
    out_path = "data/gatherable_materials.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
