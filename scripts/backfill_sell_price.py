"""Backfill vendor_sell_price (item_template.SellPrice) onto the crafted
item of every recipe, across all Classic Era profession datasets. TBC and
WoW Forever profession datasets are skipped on purpose: TBC already gets
this from extract_profession_tbc.py directly using tbc-db's item_template,
and Forever's item IDs come from an entirely different beta client build
with no relationship to classic-db's IDs at all -- cross-referencing them
against classic-db doesn't just miss data, it actively assigns the WRONG
item's sell price (confirmed: id collisions produced nonsense values like
a Recipe scroll "selling" for 25c). Forever's own vendor_sell_price is set
correctly by extract_profession_forever.py from its own ItemSparse.csv.

Requires raw_data/classic/ClassicDB.sql -- run `python scripts/fetch_data.py`
first if it's missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sql_dump_utils import extract_table_sql, parse_tuples, to_int  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SQL_DUMP = os.path.join(ROOT, "raw_data", "classic", "ClassicDB.sql")

if not os.path.exists(SQL_DUMP):
    print(f"Missing {SQL_DUMP} -- run `python scripts/fetch_data.py --classic` first.")
    sys.exit(1)

with open(SQL_DUMP, "r", encoding="utf-8", errors="replace") as f:
    full_text = f.read()

item_tuples = parse_tuples(extract_table_sql(full_text, "item_template"))
sell_price_by_item = {to_int(t[0]): to_int(t[9]) for t in item_tuples}

for path in glob.glob(os.path.join(ROOT, "data", "*_recipes.json")):
    if path.endswith("_tbc_recipes.json") or path.endswith("_forever_recipes.json"):
        continue
    data = json.load(open(path, encoding="utf-8"))
    updated = 0
    for r in data["recipes"]:
        item_id = r.get("crafted_item_id")
        r["vendor_sell_price"] = sell_price_by_item.get(item_id, 0) if item_id else 0
        updated += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"{path}: backfilled vendor_sell_price on {updated} recipes")
