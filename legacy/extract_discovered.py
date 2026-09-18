"""Find Engineering recipes acquired outside trainers (schematic items:
drops, quest rewards, vendor BoE, rep rewards) by resolving every
class=9/subclass=3 (Recipe/Engineering) item's taught spell through the
same trainer->craft-spell chain, then diffing against the known
trainer-taught set already in engineering_recipes.json.
"""
import json

from extract_engineering import (
    extract_table_sql, parse_tuples, to_int, unquote, tier_for_skill,
    SPELL_EFFECT_CREATE_ITEM, SPELL_EFFECT_LEARN_SPELL,
)

with open("ClassicDB_1_12_1_z2815.sql", "r", encoding="utf-8", errors="replace") as f:
    full_text = f.read()

item_tuples = parse_tuples(extract_table_sql(full_text, "item_template"))
spell_tuples = parse_tuples(extract_table_sql(full_text, "spell_template"))

IDX_ID = 0
IDX_REAGENT = list(range(42, 50))
IDX_REAGENT_COUNT = list(range(50, 58))
IDX_EFFECT = [61, 62, 63]
IDX_EFFECT_ITEM_TYPE = [103, 104, 105]
IDX_EFFECT_TRIGGER_SPELL = [109, 110, 111]
IDX_SPELL_NAME = 119

spells_by_id = {to_int(t[IDX_ID]): t for t in spell_tuples}
item_names = {to_int(t[0]): unquote(t[3]) for t in item_tuples}


def find_craft_spell(t):
    for eff_idx, item_idx in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
        if to_int(t[eff_idx]) == SPELL_EFFECT_CREATE_ITEM:
            return t
    for eff_idx, trig_idx in zip(IDX_EFFECT, IDX_EFFECT_TRIGGER_SPELL):
        if to_int(t[eff_idx]) == SPELL_EFFECT_LEARN_SPELL:
            triggered_t = spells_by_id.get(to_int(t[trig_idx]))
            if triggered_t is not None:
                for eff_idx2, item_idx2 in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
                    if to_int(triggered_t[eff_idx2]) == SPELL_EFFECT_CREATE_ITEM:
                        return triggered_t
    return None


eng_schematics = [
    (to_int(t[0]), unquote(t[3]), to_int(t[70]))
    for t in item_tuples
    if to_int(t[1]) == 9 and to_int(t[2]) == 3
]

known = json.load(open(r"C:\Users\bruth\OneDrive\Desktop\Claude Code - AI Accessable\data\engineering_recipes.json", encoding="utf-8"))
known_craft_ids = {r["craft_spell_id"] for r in known["recipes"]}

new_recipes = []
unresolved = []
already_known = []
for schematic_item_id, schematic_name, teach_spell_id in eng_schematics:
    t = spells_by_id.get(teach_spell_id)
    if t is None:
        unresolved.append((schematic_item_id, schematic_name, teach_spell_id, "teach spell missing"))
        continue
    craft_t = find_craft_spell(t)
    if craft_t is None:
        unresolved.append((schematic_item_id, schematic_name, teach_spell_id, "no CREATE_ITEM resolved"))
        continue
    craft_spell_id = to_int(craft_t[IDX_ID])
    if craft_spell_id in known_craft_ids:
        already_known.append((schematic_item_id, schematic_name, craft_spell_id))
        continue

    crafted_item_id = None
    for eff_idx, item_idx in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
        if to_int(craft_t[eff_idx]) == SPELL_EFFECT_CREATE_ITEM:
            crafted_item_id = to_int(craft_t[item_idx])
            break

    reagents = []
    for r_idx, c_idx in zip(IDX_REAGENT, IDX_REAGENT_COUNT):
        item_id = to_int(craft_t[r_idx])
        count = to_int(craft_t[c_idx])
        if item_id != 0 and count != 0:
            reagents.append({
                "item_id": item_id,
                "item_name": item_names.get(item_id, f"Unknown Item {item_id}"),
                "count": count,
            })

    new_recipes.append({
        "schematic_item_id": schematic_item_id,
        "schematic_item_name": schematic_name,
        "teach_spell_id": teach_spell_id,
        "craft_spell_id": craft_spell_id,
        "spell_name": unquote(t[IDX_SPELL_NAME]),
        "crafted_item_id": crafted_item_id,
        "crafted_item_name": item_names.get(crafted_item_id, f"Unknown Item {crafted_item_id}"),
        "reagents": reagents,
        "acquisition": "unknown",  # needs research: drop / quest / vendor BoE / rep reward
        "source": "cmangos-classic-db",
        "confidence": "verified-reagents-unverified-acquisition",
    })

print(f"Total Engineering schematic items: {len(eng_schematics)}")
print(f"Already covered by trainer-taught set: {len(already_known)}")
print(f"New recipes found (non-trainer): {len(new_recipes)}")
print(f"Unresolved (couldn't trace to a craft spell): {len(unresolved)}")
for u in unresolved:
    print("  UNRESOLVED:", u)

print("\nNew recipes:")
for r in new_recipes:
    print(f"  [{r['schematic_item_id']}] {r['schematic_item_name']} -> {r['crafted_item_name']}  reagents={[(g['item_name'], g['count']) for g in r['reagents']]}")

with open("discovered_engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump({"new_recipes": new_recipes, "unresolved": unresolved}, f, indent=2)
