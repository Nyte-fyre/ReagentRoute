"""Reusable pipeline: extract every discoverable recipe for a given
profession in WoW Forever, from live beta client DB2 data (wago.tools,
build 1.60.1.69913, "wow_classic_beta" branch -- confirmed to be
Forever's actual client via exact string/id matches to community guides'
described "Campsite Recipes" system).

IMPORTANT LIMITATION: unlike Classic/TBC, there is no community emulator
database (cmangos-style) for Forever yet -- it launched within the last
day as of this writing, and no server-side project has published one.
That means:
  - Every recipe here is tagged acquisition="unknown". There's no
    trainer/vendor/loot/quest source to resolve it against.
  - Recipes can ONLY be discovered via a physical "teaches this recipe"
    item (Schematic/Pattern/Plans/Recipe/Formula/Blueprint). Recipes that
    are purely trainer-taught with no representative item (common for
    early-tier recipes in Classic/TBC) are INVISIBLE to this method --
    there's no trainer table to enumerate them from. Expect this dataset
    to under-count real recipes, especially at low skill levels.
  - Beta data can change before Forever's full release. Re-run
    scripts/fetch_data_forever.py periodically and re-extract.

METHODOLOGY NOTE: the wow_classic_beta build is a whole future game
state, not a delta -- it carries forward all currently-live content
(including Season of Discovery, which ships within the classic_era
client lineage rather than a separate branch) as a baseline, plus
whatever is genuinely new to Forever on top. A first pass of this script
extracted everything present in the beta build, which meant carried-
forward SoD content (e.g. "Scarlet Soldier's Grips", an SoD Phase 8
item) showed up mislabeled as Forever content. Fixed by diffing every
recipe's spell ID against the live Classic Era client's own recipe list
(see load_classic_era_baseline_spells()) and keeping only what's absent
there -- the same before/after approach a third-party site,
foreverdiff.com, independently uses on this identical build (confirmed:
their newest indexed build is also 1.60.1.69913).

Requires raw_data/forever/*.csv -- run `python scripts/fetch_data_forever.py`
first if they're missing.

Usage: python scripts/extract_profession_forever.py <name> <skill_line_id> <item_subclass>
Example: python scripts/extract_profession_forever.py Engineering 202 3

Skill line ids / item subclasses verified empirically against this
build's own Item/SkillLineAbility data -- so far confirmed identical to
Classic/TBC's mapping: First Aid=129/7, Blacksmithing=164/4,
Leatherworking=165/1, Alchemy=171/6, Cooking=185/5, Tailoring=197/2,
Engineering=202/3, Enchanting=333/8. No Jewelcrafting item subclass (10)
found in this build -- matches community guides listing Forever's
professions without Jewelcrafting.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

RAW = os.path.join(ROOT, "raw_data", "forever")

SPELL_EFFECT_CREATE_ITEM = 24
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_ENCHANT_ITEM_PERMANENT = 53
SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY = 54
CRAFT_EFFECTS = {SPELL_EFFECT_CREATE_ITEM, SPELL_EFFECT_ENCHANT_ITEM_PERMANENT, SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY}
ITEM_EFFECT_TRIGGER_LEARN = 6  # verified against TBC and this build alike


def tier_for_skill(value):
    if value <= 75:
        return "Apprentice"
    if value <= 150:
        return "Journeyman"
    if value <= 225:
        return "Expert"
    if value <= 300:
        return "Artisan"
    return "Master"


def load_csv(name):
    path = os.path.join(RAW, f"{name}.csv")
    if not os.path.exists(path):
        print(f"Missing {path} -- run `python scripts/fetch_data_forever.py` first.")
        sys.exit(1)
    return list(csv.DictReader(open(path, encoding="utf-8")))


def load_classic_era_baseline_spells(skill_line_id):
    """Recipe spell IDs already present in the LIVE Classic Era client
    (wago.tools wow_classic_era build 1.15.9.69722 -- data/SkillLineAbility_
    classic1x.csv, same wago.tools pipeline as this Forever pull, not the
    older cmangos classic-db dump the rest of Classic Era's own extraction
    uses) for this skill line.

    Why this matters: a beta client build represents the game's whole
    future state, not a delta -- it necessarily carries forward all
    currently-live content as a baseline, including Season of Discovery
    (which ships WITHIN the classic_era client lineage, not a separate
    branch -- confirmed empirically: item 238292 "Scarlet Soldier's
    Grips", added in SoD patch 1.15.7, exists byte-identical in the live
    1.15.9 classic_era build's own Item table, and its recipe spell
    1224636 is in this exact file). Diffing against this baseline is what
    separates genuinely Forever-exclusive content from SoD/vanilla
    content that merely happens to also be present in the beta build --
    matching the same before/after methodology a third-party site
    (foreverdiff.com) independently uses on this identical build."""
    path = os.path.join(ROOT, "data", "SkillLineAbility_classic1x.csv")
    rows = csv.DictReader(open(path, encoding="utf-8"))
    return {int(r["Spell"]) for r in rows if r["SkillLine"] == str(skill_line_id)}


def load_spell_reagents(rows):
    reagents = {}
    for row in rows:
        spell_id = int(row["SpellID"])
        pairs = []
        for i in range(8):
            item_id = int(row.get(f"Reagent_{i}") or 0)
            count = int(row.get(f"ReagentCount_{i}") or 0)
            if item_id and count:
                pairs.append((item_id, count))
        if pairs:
            reagents.setdefault(spell_id, []).extend(pairs)
    return reagents


def load_spell_effects(rows):
    effects = {}
    for row in rows:
        spell_id = int(row["SpellID"])
        effect_code = int(row["Effect"].split()[0])
        item_type = int(row.get("EffectItemType") or 0)
        trigger_spell = int(row.get("EffectTriggerSpell") or 0)
        effects.setdefault(spell_id, []).append((effect_code, item_type, trigger_spell))
    return effects


def load_item_teach_spells(item_effect_rows, join_rows):
    """ItemID -> SpellID, for TriggerType==6 rows only. This build splits
    the relationship into two tables (Item <-> ItemXItemEffect <-> ItemEffect)
    instead of TBC's flat ItemEffect.ParentItemID."""
    effect_by_id = {row["ID"]: row for row in item_effect_rows}
    out = {}
    for row in join_rows:
        effect = effect_by_id.get(row["ItemEffectID"])
        if effect and int(effect["TriggerType"]) == ITEM_EFFECT_TRIGGER_LEARN:
            out[int(row["ItemID"])] = int(effect["SpellID"])
    return out


def find_craft_effect(spell_id, spell_effects):
    for effect_code, item_type, _ in spell_effects.get(spell_id, []):
        if effect_code in CRAFT_EFFECTS:
            return spell_id, effect_code, item_type
    for effect_code, _, trigger_spell in spell_effects.get(spell_id, []):
        if effect_code == SPELL_EFFECT_LEARN_SPELL and trigger_spell:
            for ec2, it2, _ in spell_effects.get(trigger_spell, []):
                if ec2 in CRAFT_EFFECTS:
                    return trigger_spell, ec2, it2
    return None


def run(profession_name, skill_line_id, item_subclass):
    print("Loading DB2 CSVs...")
    item_rows = load_csv("Item")
    item_sparse_rows = load_csv("ItemSparse")
    item_effect_rows = load_csv("ItemEffect")
    join_rows = load_csv("ItemXItemEffect")
    spell_reagent_rows = load_csv("SpellReagents")
    spell_effect_rows = load_csv("SpellEffect")
    skill_line_ability_rows = load_csv("SkillLineAbility")

    item_class_by_id = {int(r["ID"]): (int(r["ClassID"]), int(r["SubclassID"].split()[0])) for r in item_rows}
    item_names = {int(r["ID"]): r["Display_lang"] for r in item_sparse_rows if r.get("Display_lang")}
    sell_price_by_item = {int(r["ID"]): int(r["SellPrice"] or 0) for r in item_sparse_rows}
    required_skill_rank = {int(r["ID"]): int(r["RequiredSkillRank"] or 0) for r in item_sparse_rows}

    spell_reagents = load_spell_reagents(spell_reagent_rows)
    spell_effects = load_spell_effects(spell_effect_rows)
    item_teach_spells = load_item_teach_spells(item_effect_rows, join_rows)

    def reagents_of(spell_id):
        return [
            {"item_id": iid, "item_name": item_names.get(iid, f"Unknown Item {iid}"), "count": count}
            for iid, count in spell_reagents.get(spell_id, [])
        ]

    def build_recipe(teach_spell_id, craft_spell_id, effect_code, item_type, req_skill_value, item_id, item_name):
        crafted_item_id = item_type if effect_code == SPELL_EFFECT_CREATE_ITEM else None
        crafted_item_name = item_names.get(crafted_item_id, f"Unknown Item {crafted_item_id}") if crafted_item_id else f"spell:{craft_spell_id}"
        return {
            "spell_id": teach_spell_id, "craft_spell_id": craft_spell_id,
            "crafted_item_id": crafted_item_id, "crafted_item_name": crafted_item_name,
            "required_skill_value": req_skill_value, "skill_tier": tier_for_skill(req_skill_value),
            "reagents": reagents_of(craft_spell_id), "auto_granted": False,
            "learned_from": {"type": "schematic_item", "item_id": item_id, "item_name": item_name},
            "vendor_sell_price": sell_price_by_item.get(crafted_item_id, 0) if crafted_item_id else 0,
            "acquisition": "unknown",
            "acquisition_note": "No community emulator database exists yet for WoW Forever (beta) -- "
                                 "acquisition (trainer/vendor/drop/quest) is unresolved.",
            "source": "wago-tools-db2-forever-beta", "confidence": "verified-reagents-unverified-acquisition",
        }

    print("Finding recipe items (class=9, Recipe) for this profession...")
    recipe_items = [
        (item_id, item_names.get(item_id, f"Unknown Item {item_id}"), item_teach_spells.get(item_id, 0))
        for item_id, (class_id, subclass_id) in item_class_by_id.items()
        if class_id == 9 and subclass_id == item_subclass
    ]
    recipe_items = [r for r in recipe_items if r[2]]
    print(f"  {len(recipe_items)} recipe items with a resolved teach-spell.")

    by_spell = {int(r["Spell"]): r for r in skill_line_ability_rows if r["SkillLine"] == str(skill_line_id)}

    recipes = {}
    unreliable_skill_count = 0
    cross_profession_skipped = 0
    for item_id, item_name, teach_spell_id in recipe_items:
        found = find_craft_effect(teach_spell_id, spell_effects)
        if found is None:
            continue
        craft_spell_id, effect_code, item_type = found
        if craft_spell_id in recipes:
            continue
        # find_craft_effect() chases a LEARN_SPELL hop wherever it leads --
        # it doesn't know or care which profession the resolved craft
        # spell actually belongs to. Verified real bug: an Alchemy-classed
        # recipe item's chain resolved to spell 1224636, which
        # SkillLineAbility.csv confirms is registered under Blacksmithing
        # (164), not Alchemy (171) -- it showed up as a fake Alchemy
        # recipe with the Blacksmithing item's reagents attached. Require
        # the resolved spell to actually be registered under THIS
        # profession's own skill line before accepting it.
        if craft_spell_id not in by_spell:
            cross_profession_skipped += 1
            continue

        # Prefer the item's own RequiredSkillRank; it's verified reliable
        # for Classic/TBC. In this beta build it's frequently unpopulated
        # (0) even for obviously high-tier items (verified: e.g. Gnomish
        # Battle Chicken's schematic shows RequiredSkillRank=0 despite
        # needing Mithril/Truesilver reagents) -- fall back to
        # TrivialSkillLineRankLow (where it stops being Orange) from
        # SkillLineAbility, which is populated and sane, rather than
        # defaulting to a misleading "skill 1".
        item_field_skill = required_skill_rank.get(item_id) or 0
        sla_row = by_spell.get(craft_spell_id)
        trivial_low = int(sla_row["TrivialSkillLineRankLow"]) if sla_row else None
        if item_field_skill:
            req_skill = item_field_skill
        elif trivial_low:
            req_skill = trivial_low
            unreliable_skill_count += 1
        else:
            req_skill = 1
            unreliable_skill_count += 1

        recipes[craft_spell_id] = build_recipe(teach_spell_id, craft_spell_id, effect_code, item_type, req_skill, item_id, item_name)
        if sla_row:
            recipes[craft_spell_id]["trivial_low"] = trivial_low
            recipes[craft_spell_id]["trivial_high"] = int(sla_row["TrivialSkillLineRankHigh"])
        else:
            recipes[craft_spell_id]["trivial_low"] = None
            recipes[craft_spell_id]["trivial_high"] = None
        if req_skill == trivial_low and item_field_skill == 0:
            recipes[craft_spell_id]["skill_value_source"] = "trivial_low_fallback"
    matched = sum(1 for r in recipes.values() if r["trivial_low"] is not None)
    print(f"  {cross_profession_skipped} recipe items skipped -- resolved craft spell belongs to a different profession's skill line.")
    print(f"  {len(recipes)} recipes resolved with full reagent data.")
    print(f"  Matched {matched}/{len(recipes)} recipes with real thresholds.")
    print(f"  {unreliable_skill_count} recipes had no item-level skill requirement -- used trivial_low or defaulted to 1 instead.")

    print("Filtering out recipes already present in the live Classic Era client "
          "(carried-forward/Season of Discovery content, not Forever-specific)...")
    baseline_spells = load_classic_era_baseline_spells(skill_line_id)
    carried_forward = {k: v for k, v in recipes.items() if k in baseline_spells}
    recipes = {k: v for k, v in recipes.items() if k not in baseline_spells}
    print(f"  {len(carried_forward)} recipes excluded as already present in Classic Era.")
    print(f"  {len(recipes)} recipes remain as genuinely Forever-specific.")

    out = {
        "profession": profession_name, "skill_line_id": skill_line_id,
        "game_version": "forever-beta",
        "recipe_count": len(recipes), "recipes": list(recipes.values()),
        "known_limitation": "Recipe discovery is item-based only (no trainer table exists yet for "
                             "Forever) -- pure trainer-only recipes with no representative item are "
                             "missing from this dataset. Acquisition is unresolved for everything. "
                             "Recipes already present in the live Classic Era client (e.g. Season of "
                             "Discovery content, which ships within the classic_era client lineage, not "
                             "a separate branch) are excluded -- this file is genuinely Forever-specific "
                             "content only, diffed against Classic Era the same way foreverdiff.com does "
                             "on this identical build.",
    }
    out_path = os.path.join(ROOT, "data", f"{profession_name.lower().replace(' ', '_')}_forever_recipes.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path} ({len(recipes)} recipes)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
