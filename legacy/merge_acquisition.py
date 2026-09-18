import json

base = json.load(open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", encoding="utf-8"))
acq = json.load(open("engineering_acquisition.json", encoding="utf-8"))

by_item = {}
for kind in ("vendor", "drop", "quest", "multiple"):
    for e in acq[kind]:
        by_item[e["item_id"]] = {"type": kind, **e}
for e in acq["none_found"]:
    by_item[e["item_id"]] = {"type": "unresearched", **e}

updated = 0
for r in base["recipes"]:
    lf = r.get("learned_from")
    if not lf or lf.get("type") != "schematic_item":
        continue
    info = by_item.get(lf["item_id"])
    if info is None:
        continue
    r["acquisition"] = info["type"]
    r["acquisition_detail"] = {
        "vendors": info.get("vendors", []),
        "drops_from": info.get("drops_from", []),
        "quest_rewards": info.get("quest_rewards", []),
    }
    r["confidence"] = (
        "verified" if info["type"] in ("vendor", "drop", "quest")
        else "verified-reagents-unverified-acquisition"
    )
    updated += 1

with open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump(base, f, indent=2)

print("Updated acquisition info on", updated, "recipes")
from collections import Counter
print(Counter(r.get("acquisition", "trainer") for r in base["recipes"]))
print(Counter(r["confidence"] for r in base["recipes"]))
