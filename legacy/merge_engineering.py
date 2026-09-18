import json

base = json.load(open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", encoding="utf-8"))
disc = json.load(open("discovered_engineering_recipes.json", encoding="utf-8"))

for r in disc["new_recipes"]:
    base["recipes"].append({
        "spell_id": r["teach_spell_id"],
        "craft_spell_id": r["craft_spell_id"],
        "spell_name": r["spell_name"],
        "crafted_item_id": r["crafted_item_id"],
        "crafted_item_name": r["crafted_item_name"],
        "required_skill_value": None,
        "skill_tier": None,
        "reagents": r["reagents"],
        "auto_granted": False,
        "learned_from": {
            "type": "schematic_item",
            "item_id": r["schematic_item_id"],
            "item_name": r["schematic_item_name"],
        },
        "acquisition": "unknown",  # drop / quest / vendor BoE / rep reward -- not yet researched
        "source": "cmangos-classic-db",
        "confidence": "verified-reagents-unverified-acquisition",
    })

base["recipe_count"] = len(base["recipes"])
with open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump(base, f, indent=2)

print("Merged. Total recipes now:", base["recipe_count"])
verified_full = sum(1 for r in base["recipes"] if r["confidence"] == "verified")
verified_partial = sum(1 for r in base["recipes"] if r["confidence"] == "verified-reagents-unverified-acquisition")
print(f"  Fully verified (trainer/starter, incl. skill tier): {verified_full}")
print(f"  Verified reagents, unverified acquisition method: {verified_partial}")
