"""Cross-reference the 81 non-trainer Engineering schematic items against
npc_vendor (sold by a vendor), creature_loot_template (mob drop), and
quest_template (quest reward) to determine how each is acquired.
"""
import json

from extract_engineering import extract_table_sql, parse_tuples, to_int, unquote

with open("ClassicDB_1_12_1_z2815.sql", "r", encoding="utf-8", errors="replace") as f:
    full_text = f.read()

vendor_tuples = parse_tuples(extract_table_sql(full_text, "npc_vendor"))
loot_tuples = parse_tuples(extract_table_sql(full_text, "creature_loot_template"))
quest_tuples = parse_tuples(extract_table_sql(full_text, "quest_template"))
creature_tuples = parse_tuples(extract_table_sql(full_text, "creature_template"))

creature_names = {to_int(t[0]): unquote(t[1]) for t in creature_tuples}

# item_id -> list of vendor npc entries
vendor_by_item = {}
for t in vendor_tuples:
    npc_entry = to_int(t[0])
    item_id = to_int(t[1])
    vendor_by_item.setdefault(item_id, []).append(npc_entry)

# item_id -> list of (creature entry, chance)
loot_by_item = {}
for t in loot_tuples:
    creature_entry = to_int(t[0])
    item_id = to_int(t[1])
    chance = t[2]
    loot_by_item.setdefault(item_id, []).append((creature_entry, chance))

# item_id -> list of quest entries (title)
IDX_Q_ID = 0
IDX_Q_TITLE = 30
IDX_Q_REWCHOICE = list(range(68, 74))
IDX_Q_REWITEM = list(range(80, 84))
quest_by_item = {}
for t in quest_tuples:
    q_id = to_int(t[IDX_Q_ID])
    title = unquote(t[IDX_Q_TITLE])
    reward_item_ids = set()
    for idx in IDX_Q_REWCHOICE + IDX_Q_REWITEM:
        iid = to_int(t[idx])
        if iid:
            reward_item_ids.add(iid)
    for iid in reward_item_ids:
        quest_by_item.setdefault(iid, []).append((q_id, title))

data = json.load(open("discovered_engineering_recipes.json", encoding="utf-8"))

results = {"vendor": [], "drop": [], "quest": [], "multiple": [], "none_found": []}
for r in data["new_recipes"]:
    item_id = r["schematic_item_id"]
    vendors = vendor_by_item.get(item_id, [])
    drops = loot_by_item.get(item_id, [])
    quests = quest_by_item.get(item_id, [])

    sources_hit = sum(bool(x) for x in (vendors, drops, quests))
    entry = {
        "item_id": item_id,
        "item_name": r["schematic_item_name"],
        "vendors": [{"npc_entry": e, "npc_name": creature_names.get(e, f"Unknown NPC {e}")} for e in vendors],
        "drops_from": [{"npc_entry": e, "npc_name": creature_names.get(e, f"Unknown NPC {e}"), "chance": c} for e, c in drops],
        "quest_rewards": [{"quest_id": q, "title": t} for q, t in quests],
    }

    if sources_hit == 0:
        results["none_found"].append(entry)
    elif sources_hit > 1:
        results["multiple"].append(entry)
    elif vendors:
        results["vendor"].append(entry)
    elif drops:
        results["drop"].append(entry)
    elif quests:
        results["quest"].append(entry)

print("=== ACQUISITION SUMMARY ===")
for k in ["vendor", "drop", "quest", "multiple", "none_found"]:
    print(f"{k}: {len(results[k])}")

print("\n--- none_found (need manual research / may be crafted-only prereq items) ---")
for e in results["none_found"]:
    print(f"  [{e['item_id']}] {e['item_name']}")

with open("engineering_acquisition.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("\nWrote engineering_acquisition.json")
