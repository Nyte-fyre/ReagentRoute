"""Reusable pipeline: extract every recipe for a given TBC profession from
the cmangos/tbc-db SQL dump (client patch 2.4.3, Fury of the Sunwell --
full TBC content), resolve acquisition method, and attach real
Orange/Yellow/Green/Grey skill-up thresholds from TBC Anniversary client
data (SkillLineAbility DB2, build 2.5.6.69795 via wago.tools).

TBC's tbc-db dump does NOT embed spell_template data (mangos-tbc reads
spells from client DBC/DB2 files directly), unlike classic-db. So reagent
and craft-effect data here comes from three DB2 CSVs pulled from
wago.tools instead: SpellReagents (reagents per spell), SpellEffect (one
row per spell+effect-index, giving the CREATE_ITEM/ENCHANT effect and the
LEARN_SPELL trainer-wrapper chain), and ItemEffect (which item teaches
which spell -- tbc-db's own item_template.spellid_1 field is broken, see
ITEM_EFFECT_TRIGGER_LEARN below) -- all verified against the actual
wow_anniversary build, same build the live TBC Anniversary realms run.

Requires raw_data/tbc/{TBCDB.sql,SpellReagents.csv,SpellEffect.csv,
ItemEffect.csv} and raw_data/classic/ClassicDB.sql -- run
`python scripts/fetch_data.py` first if they're missing.

Usage: python scripts/extract_profession_tbc.py <name> <skill_line_id> <item_subclass>
Example: python scripts/extract_profession_tbc.py Jewelcrafting 755 10

Skill line ids (verified against mangos-tbc SharedDefines.h / npc_trainer
data): First Aid=129, Blacksmithing=164, Leatherworking=165, Alchemy=171,
Herbalism=182, Cooking=185, Mining=186, Tailoring=197, Engineering=202,
Enchanting=333, Skinning=393, Jewelcrafting=755 (new in TBC).
Recipe item subclasses (verified empirically): Leatherworking=1,
Tailoring=2, Engineering=3, Blacksmithing=4, Cooking=5, Alchemy=6,
First Aid=7, Enchanting=8, Jewelcrafting=10 (new in TBC).
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sql_dump_utils import extract_table_sql, parse_tuples, unquote, to_int  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)  # so "data/..." output paths are always relative to the project root

SQL_DUMP = os.path.join(ROOT, "raw_data", "tbc", "TBCDB.sql")
CLASSIC_SQL_DUMP = os.path.join(ROOT, "raw_data", "classic", "ClassicDB.sql")
SPELL_REAGENTS_CSV = os.path.join(ROOT, "raw_data", "tbc", "SpellReagents.csv")
SPELL_EFFECT_CSV = os.path.join(ROOT, "raw_data", "tbc", "SpellEffect.csv")
ITEM_EFFECT_CSV = os.path.join(ROOT, "raw_data", "tbc", "ItemEffect.csv")
ITEM_EFFECT_TRIGGER_LEARN = 6  # verified empirically: item_template.spellid_1 is broken/defaulted
# to 483 for every single row in tbc-db (a data bug), so the "teaches this
# spell" link has to come from the modern ItemEffect DB2 table instead --
# TriggerType 0 is a shared generic "on use" filler spell, TriggerType 6 is
# the real teach link (verified: item 4408 "Schematic: Mechanical Squirrel"
# -> spell 3928 -> CREATE_ITEM 4401 "Mechanical Squirrel Box", exact match).
SKILL_LINE_ABILITY_CSV = os.path.join(ROOT, "data", "SkillLineAbility_tbc.csv")

SPELL_EFFECT_CREATE_ITEM = 24
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_ENCHANT_ITEM_PERMANENT = 53
SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY = 54
CRAFT_EFFECTS = {SPELL_EFFECT_CREATE_ITEM, SPELL_EFFECT_ENCHANT_ITEM_PERMANENT, SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY}

# item_template 0-based column indices (validated: tuple length == 141)
ITEM_ENTRY, ITEM_CLASS, ITEM_SUBCLASS, ITEM_NAME = 0, 1, 2, 4
ITEM_SELL_PRICE = 10
ITEM_REQUIRED_SKILL, ITEM_REQUIRED_SKILL_RANK = 16, 17
ITEM_SPELLID_1 = 71

# quest_template 0-based column indices (validated: tuple length == 138)
Q_ENTRY, Q_TITLE = 0, 31
Q_REWCHOICE = list(range(69, 75))
Q_REWITEM = list(range(81, 85))


def tier_for_skill(value):
    if value <= 75:
        return "Apprentice"
    if value <= 150:
        return "Journeyman"
    if value <= 225:
        return "Expert"
    if value <= 300:
        return "Artisan"
    return "Master"  # TBC adds Master tier, 300-375


def load_spell_reagents(path):
    reagents = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        spell_id = int(row["SpellID"])
        pairs = []
        for i in range(8):
            item_id = int(row[f"Reagent_{i}"] or 0)
            count = int(row[f"ReagentCount_{i}"] or 0)
            if item_id and count:
                pairs.append((item_id, count))
        if pairs:
            reagents.setdefault(spell_id, []).extend(pairs)
    return reagents


def load_item_teach_spells(path):
    """ParentItemID -> SpellID, for TriggerType==6 rows only (see constant
    docstring above for why -- item_template.spellid_1 is unusable)."""
    out = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if int(row["TriggerType"]) == ITEM_EFFECT_TRIGGER_LEARN:
            out[int(row["ParentItemID"])] = int(row["SpellID"])
    return out


def load_spell_effects(path):
    """spell_id -> list of (effect_code, effect_item_type, effect_trigger_spell)"""
    effects = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        spell_id = int(row["SpellID"])
        effect_code = int(row["Effect"].split()[0])
        item_type = int(row["EffectItemType"] or 0)
        trigger_spell = int(row["EffectTriggerSpell"] or 0)
        effects.setdefault(spell_id, []).append((effect_code, item_type, trigger_spell))
    return effects


def load_classic_learn_spell_hops():
    """Many old vanilla-era trainer-taught spells are LEARN_SPELL wrapper
    ids (e.g. teaches you the real craft spell) that have been pruned from
    modern client data entirely -- the wrapper id itself has zero effect
    rows in the TBC/Anniversary SpellEffect export (verified: e.g. spell
    7431 for Arclight Spanner). classic-db's spell_template still embeds
    this mapping (it mirrors the original 1.12 Spell.dbc), so use it as a
    fallback bridge from wrapper id -> real craft spell id."""
    with open(CLASSIC_SQL_DUMP, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    tuples = parse_tuples(extract_table_sql(text, "spell_template"))
    IDX_ID, IDX_EFFECT, IDX_TRIGGER = 0, [61, 62, 63], [109, 110, 111]
    hops = {}
    for t in tuples:
        spell_id = to_int(t[IDX_ID])
        for eff_idx, trig_idx in zip(IDX_EFFECT, IDX_TRIGGER):
            if to_int(t[eff_idx]) == SPELL_EFFECT_LEARN_SPELL:
                trig = to_int(t[trig_idx])
                if trig:
                    hops[spell_id] = trig
                break
    return hops


def find_craft_effect(spell_id, spell_effects, classic_hops=None):
    """Return (craft_spell_id, effect_code, effect_item_type) or None.
    Follows one LEARN_SPELL hop (trainer wrapper -> real craft spell),
    using modern SpellEffect data first and classic-db as a fallback
    bridge for pruned legacy wrapper spell ids (see load_classic_learn_spell_hops)."""
    classic_hops = classic_hops or {}
    for effect_code, item_type, _ in spell_effects.get(spell_id, []):
        if effect_code in CRAFT_EFFECTS:
            return spell_id, effect_code, item_type
    for effect_code, _, trigger_spell in spell_effects.get(spell_id, []):
        if effect_code == SPELL_EFFECT_LEARN_SPELL and trigger_spell:
            for ec2, it2, _ in spell_effects.get(trigger_spell, []):
                if ec2 in CRAFT_EFFECTS:
                    return trigger_spell, ec2, it2
    if spell_id in classic_hops:
        trigger_spell = classic_hops[spell_id]
        for ec2, it2, _ in spell_effects.get(trigger_spell, []):
            if ec2 in CRAFT_EFFECTS:
                return trigger_spell, ec2, it2
    return None


def run(profession_name, skill_line_id, item_subclass):
    for required in [SQL_DUMP, CLASSIC_SQL_DUMP, SPELL_REAGENTS_CSV, SPELL_EFFECT_CSV, ITEM_EFFECT_CSV]:
        if not os.path.exists(required):
            print(f"Missing {required} -- run `python scripts/fetch_data.py --tbc` first.")
            sys.exit(1)

    print("Loading SQL dumps...")
    with open(SQL_DUMP, "r", encoding="utf-8", errors="replace") as f:
        full_text = f.read()
    with open(CLASSIC_SQL_DUMP, "r", encoding="utf-8", errors="replace") as f:
        classic_text = f.read()

    tables = {}
    for name in ["item_template", "creature_loot_template", "quest_template",
                 "creature_template", "reference_loot_template", "item_loot_template",
                 "fishing_loot_template"]:
        # Verified complete, self-sufficient snapshots in tbc-db (include legacy
        # classic content carried forward) -- no merge needed.
        tables[name] = parse_tuples(extract_table_sql(full_text, name))

    # npc_trainer and npc_vendor are verified INCREMENTAL-ONLY in tbc-db (e.g.
    # tbc-db has only 388 total npc_trainer rows vs classic-db's ~thousands,
    # and only 2 Engineering entries vs classic-db's 452) -- tbc-db assumes a
    # classic-db base layered underneath, per the mangos-tbc project's own
    # architecture. Union both, with tbc-db rows taking precedence on
    # (entry, spell)/(entry, item) conflicts.
    for name, key_idx in [("npc_trainer", (0, 1)), ("npc_vendor", (0, 1))]:
        classic_rows = parse_tuples(extract_table_sql(classic_text, name))
        tbc_rows = parse_tuples(extract_table_sql(full_text, name))
        merged = {}
        for t in classic_rows:
            merged[(to_int(t[key_idx[0]]), to_int(t[key_idx[1]]))] = t
        for t in tbc_rows:
            merged[(to_int(t[key_idx[0]]), to_int(t[key_idx[1]]))] = t
        tables[name] = list(merged.values())
        print(f"  {name}: {len(classic_rows)} classic + {len(tbc_rows)} tbc -> {len(tables[name])} merged")

    print("Loading SpellReagents / SpellEffect / ItemEffect DB2 data...")
    spell_reagents = load_spell_reagents(SPELL_REAGENTS_CSV)
    spell_effects = load_spell_effects(SPELL_EFFECT_CSV)
    item_teach_spells = load_item_teach_spells(ITEM_EFFECT_CSV)
    print("Loading classic-db LEARN_SPELL hop bridge for pruned legacy wrapper spells...")
    classic_hops = load_classic_learn_spell_hops()

    item_names = {to_int(t[ITEM_ENTRY]): unquote(t[ITEM_NAME]) for t in tables["item_template"]}
    creature_names = {to_int(t[0]): unquote(t[1]) for t in tables["creature_template"]}
    required_skill_rank = {to_int(t[ITEM_ENTRY]): to_int(t[ITEM_REQUIRED_SKILL_RANK]) for t in tables["item_template"]}
    vendor_sell_price = {to_int(t[ITEM_ENTRY]): to_int(t[ITEM_SELL_PRICE]) for t in tables["item_template"]}

    def reagents_of(spell_id):
        return [
            {"item_id": iid, "item_name": item_names.get(iid, f"Unknown Item {iid}"), "count": count}
            for iid, count in spell_reagents.get(spell_id, [])
        ]

    def build_recipe(teach_spell_id, craft_spell_id, effect_code, item_type, req_skill_value, learned_from):
        crafted_item_id = item_type if effect_code == SPELL_EFFECT_CREATE_ITEM else None
        crafted_item_name = item_names.get(crafted_item_id, f"Unknown Item {crafted_item_id}") if crafted_item_id else f"spell:{craft_spell_id}"
        return {
            "spell_id": teach_spell_id, "craft_spell_id": craft_spell_id,
            "crafted_item_id": crafted_item_id, "crafted_item_name": crafted_item_name,
            "required_skill_value": req_skill_value, "skill_tier": tier_for_skill(req_skill_value),
            "reagents": reagents_of(craft_spell_id), "auto_granted": False,
            "learned_from": learned_from,
            "vendor_sell_price": vendor_sell_price.get(crafted_item_id, 0) if crafted_item_id else 0,
            "source": "cmangos-tbc-db+wago-tools-db2", "confidence": "verified",
        }

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

    recipes = {}
    for spell_id, req_skill_value in trainer_taught.items():
        found = find_craft_effect(spell_id, spell_effects, classic_hops)
        if found is None:
            continue
        craft_spell_id, effect_code, item_type = found
        recipes[craft_spell_id] = build_recipe(
            spell_id, craft_spell_id, effect_code, item_type, req_skill_value, {"type": "trainer"}
        )
    print(f"  {len(recipes)} trainer-taught recipes resolved.")

    # ---- 2. schematic/pattern/formula/design item-taught recipes ----
    print("Resolving recipe-item-taught recipes...")
    recipe_items = [
        (to_int(t[ITEM_ENTRY]), unquote(t[ITEM_NAME]), item_teach_spells.get(to_int(t[ITEM_ENTRY]), 0))
        for t in tables["item_template"]
        if to_int(t[ITEM_CLASS]) == 9 and to_int(t[ITEM_SUBCLASS]) == item_subclass
    ]
    recipe_items = [r for r in recipe_items if r[2]]  # drop items with no resolved teach spell
    new_count = 0
    schematic_recipes = {}
    for item_id, item_name, teach_spell_id in recipe_items:
        found = find_craft_effect(teach_spell_id, spell_effects, classic_hops)
        if found is None:
            continue
        craft_spell_id, effect_code, item_type = found
        if craft_spell_id in recipes:
            continue
        req_skill = required_skill_rank.get(item_id) or 1
        rec = build_recipe(
            teach_spell_id, craft_spell_id, effect_code, item_type, req_skill,
            {"type": "schematic_item", "item_id": item_id, "item_name": item_name},
        )
        rec["confidence"] = "verified-reagents-unverified-acquisition"
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
        q_id, title = to_int(t[Q_ENTRY]), unquote(t[Q_TITLE])
        for idx in Q_REWCHOICE + Q_REWITEM:
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
        else:
            kinds = [k for k, _ in findings]
            rec["acquisition"] = kinds[0] if len(set(kinds)) == 1 else "multiple"
            rec["acquisition_note"] = "; ".join(n for _, n in findings[:3])
            rec["confidence"] = "verified"

    acq_counts = {}
    for rec in schematic_recipes.values():
        acq_counts[rec["acquisition"]] = acq_counts.get(rec["acquisition"], 0) + 1
    print(f"  Acquisition breakdown for non-trainer recipes: {acq_counts}")

    for rec in recipes.values():
        rec.setdefault("acquisition", "trainer")

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
        "game_version": "tbc-anniversary",
        "recipe_count": len(recipes), "recipes": list(recipes.values()),
    }
    out_path = os.path.join(ROOT, "data", f"{profession_name.lower().replace(' ', '_')}_tbc_recipes.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path} ({len(recipes)} recipes)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
