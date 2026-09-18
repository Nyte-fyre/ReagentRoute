import json

base = json.load(open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", encoding="utf-8"))
deep = json.load(open("engineering_acquisition_deep.json", encoding="utf-8"))

# manually curated summaries from the deep pass + Wowhead cross-check for the 2 that
# needed a live lookup (source: cmangos-classic-db for the loot-table hits,
# source: wowhead for the 2 not present in any local table at all)
overrides = {
    4408: {"acquisition": "drop", "note": "generic world-drop loot pool (#50502/#50503), ~800 creatures", "confidence": "verified"},
    17720: {"acquisition": "quest", "note": "inside 'Smokywood Pastures Special Gift' container from Winter Veil quest 'A Smokywood Pastures Thank You!'", "confidence": "verified"},
    18290: {"acquisition": "drop", "note": "Molten Core shared loot pool #34011 (Magmadar/Golemagg/Baron Geddon/Garr/Lucifron/Gehennas/+1)", "confidence": "verified"},
    18291: {"acquisition": "drop", "note": "Molten Core shared loot pool #34011 (Magmadar/Golemagg/Baron Geddon/Garr/Lucifron/Gehennas/+1)", "confidence": "verified"},
    18292: {"acquisition": "drop", "note": "Molten Core shared loot pool #34011 (Magmadar/Golemagg/Baron Geddon/Garr/Lucifron/Gehennas/+1)", "confidence": "verified"},
    18655: {"acquisition": "drop", "note": "world gameobject loot (chest, gameobject entry 16577) via shared loot pool #35037", "confidence": "verified"},
    21724: {"acquisition": "quest", "note": "inside container item 21740, quest 'Small Rockets' (8876)", "confidence": "verified"},
    21725: {"acquisition": "quest", "note": "inside container item 21740, quest 'Small Rockets' (8876)", "confidence": "verified"},
    21726: {"acquisition": "quest", "note": "inside container item 21740, quest 'Small Rockets' (8876)", "confidence": "verified"},
    21727: {"acquisition": "quest", "note": "inside container item 21742, quest 'Large Rockets' (8879)", "confidence": "verified"},
    21728: {"acquisition": "quest", "note": "inside container item 21742, quest 'Large Rockets' (8879)", "confidence": "verified"},
    21729: {"acquisition": "quest", "note": "inside container item 21742, quest 'Large Rockets' (8879)", "confidence": "verified"},
    21730: {"acquisition": "quest", "note": "inside container item 21741, quest 'Cluster Rockets' (8880)", "confidence": "verified"},
    21731: {"acquisition": "quest", "note": "inside container item 21741, quest 'Cluster Rockets' (8880)", "confidence": "verified"},
    21732: {"acquisition": "quest", "note": "inside container item 21741, quest 'Cluster Rockets' (8880)", "confidence": "verified"},
    21733: {"acquisition": "quest", "note": "inside container item 21743, quest 'Large Cluster Rockets' (8881)", "confidence": "verified"},
    21734: {"acquisition": "quest", "note": "inside container item 21743, quest 'Large Cluster Rockets' (8881)", "confidence": "verified"},
    21735: {"acquisition": "quest", "note": "inside container item 21743, quest 'Large Cluster Rockets' (8881)", "confidence": "verified"},
    22729: {"acquisition": "vendor", "note": "Darkmoon Faire ticket vendor, 40 tickets (per Wowhead; not in local vendor table -- currency-exchange mechanic)", "confidence": "verified-cross-checked-wowhead"},
    18235: {"acquisition": "unknown", "note": "no source found in DB or on Wowhead; likely a rare/unconfirmed world drop", "confidence": "unresearched"},
}

updated = 0
for r in base["recipes"]:
    lf = r.get("learned_from")
    if not lf or lf.get("type") != "schematic_item":
        continue
    iid = lf["item_id"]
    if iid in overrides:
        o = overrides[iid]
        r["acquisition"] = o["acquisition"]
        r["acquisition_note"] = o["note"]
        r["confidence"] = o["confidence"]
        updated += 1

with open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump(base, f, indent=2)

print("Updated", updated, "recipes with deep acquisition data")
from collections import Counter
print("Acquisition:", Counter(r.get("acquisition", "trainer") for r in base["recipes"]))
print("Confidence:", Counter(r["confidence"] for r in base["recipes"]))
