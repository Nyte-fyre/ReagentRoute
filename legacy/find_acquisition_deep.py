"""Deeper acquisition pass for the schematics find_acquisition.py couldn't
resolve: follow fishing_loot_template directly, reference_loot_template
(shared boss loot pools, reverse-linked via negative mincountOrRef in
creature_loot_template), and item_loot_template (container contents,
reverse-linked to whatever grants the container item).
"""
import json

from extract_engineering import extract_table_sql, parse_tuples, to_int, unquote

with open("ClassicDB_1_12_1_z2815.sql", "r", encoding="utf-8", errors="replace") as f:
    full_text = f.read()

def load_loot_table(name):
    tuples = parse_tuples(extract_table_sql(full_text, name))
    by_item = {}
    by_entry_negref = {}  # entry -> list of (item, mincountOrRef) where mincountOrRef < 0 (reference row)
    for t in tuples:
        entry = to_int(t[0])
        item = to_int(t[1])
        mincount_or_ref = to_int(t[4])
        by_item.setdefault(item, []).append(entry)
    return tuples, by_item

creature_loot_tuples, creature_loot_by_item = load_loot_table("creature_loot_template")
reference_loot_tuples, reference_loot_by_item = load_loot_table("reference_loot_template")
item_loot_tuples, item_loot_by_item = load_loot_table("item_loot_template")
fishing_loot_tuples, fishing_loot_by_item = load_loot_table("fishing_loot_template")
quest_tuples = parse_tuples(extract_table_sql(full_text, "quest_template"))
vendor_tuples = parse_tuples(extract_table_sql(full_text, "npc_vendor"))
creature_tuples = parse_tuples(extract_table_sql(full_text, "creature_template"))

creature_names = {to_int(t[0]): unquote(t[1]) for t in creature_tuples}

# reference entry -> list of creature entries that point to it (negative mincountOrRef == -reference_entry)
creatures_using_reference = {}
for t in creature_loot_tuples:
    creature_entry = to_int(t[0])
    mincount_or_ref = to_int(t[4])
    if mincount_or_ref < 0:
        ref_entry = -mincount_or_ref
        creatures_using_reference.setdefault(ref_entry, []).append(creature_entry)

# item_id -> quests that reward it directly (rebuild same as before)
IDX_Q_TITLE = 30
IDX_Q_REWCHOICE = list(range(68, 74))
IDX_Q_REWITEM = list(range(80, 84))
quest_by_item = {}
for t in quest_tuples:
    q_id = to_int(t[0])
    title = unquote(t[IDX_Q_TITLE])
    for idx in IDX_Q_REWCHOICE + IDX_Q_REWITEM:
        iid = to_int(t[idx])
        if iid:
            quest_by_item.setdefault(iid, []).append((q_id, title))

vendor_by_item = {}
for t in vendor_tuples:
    npc_entry = to_int(t[0])
    item_id = to_int(t[1])
    vendor_by_item.setdefault(item_id, []).append(npc_entry)


def describe(item_id, depth=0, seen=None):
    if seen is None:
        seen = set()
    if item_id in seen or depth > 4:
        return []
    seen.add(item_id)
    findings = []

    for e in creature_loot_by_item.get(item_id, []):
        findings.append(f"dropped by creature entry {e} ({creature_names.get(e, '?')})")

    for e in fishing_loot_by_item.get(item_id, []):
        findings.append(f"fished (fishing_loot_template zone entry {e})")

    for e in reference_loot_by_item.get(item_id, []):
        # e is the reference_loot_template entry id containing this item
        creatures = creatures_using_reference.get(e, [])
        if creatures:
            names = [creature_names.get(c, f"?{c}") for c in creatures[:6]]
            more = f" (+{len(creatures)-6} more)" if len(creatures) > 6 else ""
            findings.append(f"in shared loot pool #{e}, used by: {', '.join(names)}{more}")
        else:
            findings.append(f"in shared loot pool #{e} (no creature found using it directly)")

    for v in vendor_by_item.get(item_id, []):
        findings.append(f"sold by vendor npc entry {v} ({creature_names.get(v, '?')})")

    for q, title in quest_by_item.get(item_id, []):
        findings.append(f"quest reward: '{title}' (id {q})")

    for container_entry in item_loot_by_item.get(item_id, []):
        # container_entry is the item id of the container holding item_id -- recurse to find how to get the container
        sub = describe(container_entry, depth + 1, seen)
        if sub:
            for s in sub:
                findings.append(f"inside container item {container_entry} <- {s}")
        else:
            findings.append(f"inside container item {container_entry} (container source unknown)")

    return findings


targets = [4408, 17720, 18290, 18291, 18292, 18655, 21724, 21725, 21726, 21727,
           21728, 21729, 21730, 21731, 21732, 21733, 21734, 21735, 22729, 18235]

names = json.load(open("discovered_engineering_recipes.json", encoding="utf-8"))
name_by_id = {r["schematic_item_id"]: r["schematic_item_name"] for r in names["new_recipes"]}

results = {}
for item_id in targets:
    findings = describe(item_id)
    results[item_id] = {"name": name_by_id.get(item_id, "?"), "findings": findings}
    print(f"[{item_id}] {name_by_id.get(item_id,'?')}")
    if findings:
        for f in findings:
            print("   -", f)
    else:
        print("   - NOTHING FOUND in any loot/vendor/quest table")

with open("engineering_acquisition_deep.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
