"""Reusable pipeline: extract every recipe for a given Classic profession
from the cmangos/classic-db SQL dump, resolve acquisition method (trainer,
vendor, drop, quest -- including reference/container/fishing indirection),
and attach real Orange/Yellow/Green/Grey skill-up thresholds from Classic
Era client data (SkillLineAbility.dbc). Consolidates the pipeline built
and verified against Engineering into one reusable, parameterized script.

Requires raw_data/classic/ClassicDB.sql -- run `python scripts/fetch_data.py`
first if it's missing.

Usage: python scripts/extract_profession.py <name> <skill_line_id> <item_subclass>
Example: python scripts/extract_profession.py Blacksmithing 164 4

Known skill line ids (verified against mangos-classic SharedDefines.h):
  First Aid=129, Blacksmithing=164, Leatherworking=165, Alchemy=171,
  Herbalism=182, Cooking=185, Mining=186, Tailoring=197, Engineering=202,
  Enchanting=333, Skinning=393
Known recipe item subclasses (verified empirically against item_template):
  Leatherworking=1, Tailoring=2, Engineering=3, Blacksmithing=4,
  Cooking=5, Alchemy=6, First Aid=7, Enchanting=8
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sql_dump_utils import extract_table_sql, parse_tuples, unquote, to_int  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)  # so "data/..." output paths are always relative to the project root

SQL_DUMP = os.path.join(ROOT, "raw_data", "classic", "ClassicDB.sql")
SKILL_LINE_ABILITY_CSV = os.path.join(ROOT, "data", "SkillLineAbility_classic1x.csv")

SPELL_EFFECT_CREATE_ITEM = 24
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_ENCHANT_ITEM_PERMANENT = 53
SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY = 54
CRAFT_EFFECTS = {SPELL_EFFECT_CREATE_ITEM, SPELL_EFFECT_ENCHANT_ITEM_PERMANENT, SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY}

# spell_template 0-based column indices (validated against actual tuple
# length == 153 for this dump)
IDX_ID = 0
IDX_REAGENT = list(range(42, 50))
IDX_REAGENT_COUNT = list(range(50, 58))
IDX_EFFECT = [61, 62, 63]
IDX_EFFECT_ITEM_TYPE = [103, 104, 105]
IDX_EFFECT_TRIGGER_SPELL = [109, 110, 111]
IDX_SPELL_NAME = 119

# item_template 0-based column indices (validated: tuple length == 128)
ITEM_ENTRY, ITEM_CLASS, ITEM_SUBCLASS, ITEM_NAME = 0, 1, 2, 3
ITEM_REQUIRED_SKILL, ITEM_REQUIRED_SKILL_RANK = 15, 16
ITEM_SPELLID_1 = 70


def tier_for_skill(value):
    if value <= 75:
        return "Apprentice"
    if value <= 150:
        return "Journeyman"
    if value <= 200:
        return "Expert"
    return "Artisan"


def find_craft_spell(t, spells_by_id):
    for eff_idx in IDX_EFFECT:
        if to_int(t[eff_idx]) in CRAFT_EFFECTS:
            return t
    for eff_idx, trig_idx in zip(IDX_EFFECT, IDX_EFFECT_TRIGGER_SPELL):
        if to_int(t[eff_idx]) == SPELL_EFFECT_LEARN_SPELL:
            triggered_t = spells_by_id.get(to_int(t[trig_idx]))
            if triggered_t is not None:
                for eff_idx2 in IDX_EFFECT:
                    if to_int(triggered_t[eff_idx2]) in CRAFT_EFFECTS:
                        return triggered_t
    return None


def reagents_of(craft_t, item_names):
    out = []
    for r_idx, c_idx in zip(IDX_REAGENT, IDX_REAGENT_COUNT):
        item_id, count = to_int(craft_t[r_idx]), to_int(craft_t[c_idx])
        if item_id and count:
            out.append({"item_id": item_id, "item_name": item_names.get(item_id, f"Unknown Item {item_id}"), "count": count})
    return out


def crafted_item_of(craft_t):
    """Returns the created item id, or None if this recipe applies an
    enchant effect directly to gear rather than producing a new item."""
    for eff_idx, item_idx in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
        if to_int(craft_t[eff_idx]) == SPELL_EFFECT_CREATE_ITEM:
            return to_int(craft_t[item_idx])
    return None


def product_name(craft_t, item_names):
    item_id = crafted_item_of(craft_t)
    if item_id:
        return item_id, item_names.get(item_id, f"Unknown Item {item_id}")
    return None, unquote(craft_t[IDX_SPELL_NAME])  # enchant: name the effect itself


def run(profession_name, skill_line_id, item_subclass):
    if not os.path.exists(SQL_DUMP):
        print(f"Missing {SQL_DUMP} -- run `python scripts/fetch_data.py --classic` first.")
        sys.exit(1)

    print("Loading SQL dump...")
    with open(SQL_DUMP, "r", encoding="utf-8", errors="replace") as f:
        full_text = f.read()

    tables = {}
    for name in ["npc_trainer", "item_template", "spell_template", "npc_vendor",
                 "creature_loot_template", "quest_template", "creature_template",
                 "reference_loot_template", "item_loot_template", "fishing_loot_template"]:
        tables[name] = parse_tuples(extract_table_sql(full_text, name))

    item_names = {to_int(t[ITEM_ENTRY]): unquote(t[ITEM_NAME]) for t in tables["item_template"]}
    spells_by_id = {to_int(t[IDX_ID]): t for t in tables["spell_template"]}
    creature_names = {to_int(t[0]): unquote(t[1]) for t in tables["creature_template"]}
    required_skill_rank = {to_int(t[ITEM_ENTRY]): to_int(t[ITEM_REQUIRED_SKILL_RANK]) for t in tables["item_template"]}

    # ---- 1. trainer-taught recipes ----
    print("Resolving trainer-taught recipes...")
    trainer_taught = {}
    for t in tables["npc_trainer"]:
        if to_int(t[3]) != skill_line_id:
            continue
        spell_id, reqskillvalue = to_int(t[1]), to_int(t[4])
        prev = trainer_taught.get(spell_id)
        if prev is None or reqskillvalue < prev:
            trainer_taught[spell_id] = reqskillvalue

    recipes = {}  # craft_spell_id -> recipe dict
    for spell_id, req_skill_value in trainer_taught.items():
        t = spells_by_id.get(spell_id)
        if t is None:
            continue
        craft_t = find_craft_spell(t, spells_by_id)
        if craft_t is None:
            continue
        craft_spell_id = to_int(craft_t[IDX_ID])
        crafted_item_id, crafted_item_name = product_name(craft_t, item_names)
        recipes[craft_spell_id] = {
            "spell_id": spell_id, "craft_spell_id": craft_spell_id,
            "spell_name": unquote(t[IDX_SPELL_NAME]),
            "crafted_item_id": crafted_item_id,
            "crafted_item_name": crafted_item_name,
            "required_skill_value": req_skill_value, "skill_tier": tier_for_skill(req_skill_value),
            "reagents": reagents_of(craft_t, item_names), "auto_granted": False,
            "learned_from": {"type": "trainer"},
            "acquisition": "trainer", "source": "cmangos-classic-db", "confidence": "verified",
        }
    print(f"  {len(recipes)} trainer-taught recipes resolved.")

    # ---- 2. schematic/pattern/formula/etc item-taught recipes ----
    print("Resolving schematic-item-taught recipes...")
    recipe_items = [
        (to_int(t[ITEM_ENTRY]), unquote(t[ITEM_NAME]), to_int(t[ITEM_SPELLID_1]))
        for t in tables["item_template"]
        if to_int(t[ITEM_CLASS]) == 9 and to_int(t[ITEM_SUBCLASS]) == item_subclass
    ]
    new_count = 0
    schematic_recipes = {}
    for item_id, item_name, teach_spell_id in recipe_items:
        t = spells_by_id.get(teach_spell_id)
        if t is None:
            continue
        craft_t = find_craft_spell(t, spells_by_id)
        if craft_t is None:
            continue
        craft_spell_id = to_int(craft_t[IDX_ID])
        if craft_spell_id in recipes:
            continue
        crafted_item_id, crafted_item_name = product_name(craft_t, item_names)
        req_skill = required_skill_rank.get(item_id) or 1
        rec = {
            "spell_id": teach_spell_id, "craft_spell_id": craft_spell_id,
            "spell_name": unquote(t[IDX_SPELL_NAME]),
            "crafted_item_id": crafted_item_id,
            "crafted_item_name": crafted_item_name,
            "required_skill_value": req_skill, "skill_tier": tier_for_skill(req_skill),
            "reagents": reagents_of(craft_t, item_names), "auto_granted": False,
            "learned_from": {"type": "schematic_item", "item_id": item_id, "item_name": item_name},
            "source": "cmangos-classic-db", "confidence": "verified-reagents-unverified-acquisition",
        }
        recipes[craft_spell_id] = rec
        schematic_recipes[item_id] = rec
        new_count += 1
    print(f"  {new_count} additional recipes found via {len(recipe_items)} recipe items.")

    # ---- 3. acquisition resolution for schematic-taught recipes ----
    print("Resolving acquisition (vendor/drop/quest/fishing/container/reference)...")
    vendor_by_item = {}
    for t in tables["npc_vendor"]:
        vendor_by_item.setdefault(to_int(t[1]), []).append(to_int(t[0]))

    def load_loot(name):
        by_item = {}
        for t in tables[name]:
            by_item.setdefault(to_int(t[1]), []).append(to_int(t[0]))
        return by_item

    creature_loot_by_item = load_loot("creature_loot_template")
    reference_loot_by_item = load_loot("reference_loot_template")
    item_loot_by_item = load_loot("item_loot_template")
    fishing_loot_by_item = load_loot("fishing_loot_template")

    creatures_using_reference = {}
    for t in tables["creature_loot_template"]:
        m = to_int(t[4])
        if m < 0:
            creatures_using_reference.setdefault(-m, []).append(to_int(t[0]))

    quest_by_item = {}
    for t in tables["quest_template"]:
        q_id, title = to_int(t[0]), unquote(t[30])
        for idx in list(range(68, 74)) + list(range(80, 84)):
            iid = to_int(t[idx])
            if iid:
                quest_by_item.setdefault(iid, []).append((q_id, title))

    def describe(item_id, depth=0, seen=None):
        seen = seen or set()
        if item_id in seen or depth > 4:
            return []
        seen.add(item_id)
        findings = []
        if item_id in vendor_by_item:
            findings.append(("vendor", f"sold by vendor(s): {[creature_names.get(v, str(v)) for v in vendor_by_item[item_id]]}"))
        if item_id in creature_loot_by_item:
            findings.append(("drop", f"dropped by: {[creature_names.get(e, str(e)) for e in creature_loot_by_item[item_id]]}"))
        if item_id in fishing_loot_by_item:
            findings.append(("drop", "caught by fishing"))
        if item_id in reference_loot_by_item:
            for ref in reference_loot_by_item[item_id]:
                creatures = creatures_using_reference.get(ref, [])
                findings.append(("drop", f"shared loot pool #{ref}: {[creature_names.get(c, str(c)) for c in creatures[:5]]}"))
        if item_id in quest_by_item:
            for q, title in quest_by_item[item_id]:
                findings.append(("quest", f"quest reward: '{title}' ({q})"))
        if item_id in item_loot_by_item:
            for container in item_loot_by_item[item_id]:
                sub = describe(container, depth + 1, seen)
                if sub:
                    for kind, note in sub:
                        findings.append((kind, f"inside container {container} <- {note}"))
        return findings

    for item_id, rec in schematic_recipes.items():
        findings = describe(item_id)
        if not findings:
            rec["acquisition"] = "unresearched"
            rec["confidence"] = "verified-reagents-unverified-acquisition"
        else:
            kinds = [k for k, _ in findings]
            rec["acquisition"] = kinds[0] if len(set(kinds)) == 1 else "multiple"
            rec["acquisition_note"] = "; ".join(n for _, n in findings[:3])
            rec["confidence"] = "verified"

    acq_counts = {}
    for rec in schematic_recipes.values():
        acq_counts[rec["acquisition"]] = acq_counts.get(rec["acquisition"], 0) + 1
    print(f"  Acquisition breakdown for non-trainer recipes: {acq_counts}")

    # ---- 4. real skill-up thresholds ----
    print("Attaching Orange/Yellow/Green/Grey thresholds from client data...")
    sla_rows = list(csv.DictReader(open(SKILL_LINE_ABILITY_CSV, encoding="utf-8")))
    by_spell = {int(r["Spell"]): r for r in sla_rows if r["SkillLine"] == str(skill_line_id)}
    matched = 0
    for rec in recipes.values():
        row = by_spell.get(rec["craft_spell_id"])
        if row is None:
            rec["trivial_low"] = None
            rec["trivial_high"] = None
            continue
        matched += 1
        rec["trivial_low"] = int(row["TrivialSkillLineRankLow"])
        rec["trivial_high"] = int(row["TrivialSkillLineRankHigh"])
    print(f"  Matched {matched}/{len(recipes)} recipes with real thresholds.")

    out = {
        "profession": profession_name, "skill_line_id": skill_line_id,
        "recipe_count": len(recipes), "recipes": list(recipes.values()),
    }
    out_path = os.path.join(ROOT, "data", f"{profession_name.lower().replace(' ', '_')}_recipes.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path} ({len(recipes)} recipes)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
