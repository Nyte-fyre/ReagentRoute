"""Extract Engineering recipe/reagent data from the cmangos classic-db SQL dump.

Source: cmangos/classic-db, ClassicDB_1_12_1_z2815.sql (client patch 1.12 data).
Tagged source: "cmangos-classic-db", confidence: "verified" per handoff doc Step 3a.
"""
import json
import re
import sys

SQL_PATH = "ClassicDB_1_12_1_z2815.sql"
ENGINEERING_SKILL_LINE = 202  # vanilla SkillLine.dbc id for Engineering
SPELL_EFFECT_CREATE_ITEM = 24
SPELL_EFFECT_LEARN_SPELL = 36

# Starter recipes auto-granted on learning the profession (not present in
# npc_trainer since no trainer teaches them). Craft spell id -> skill level
# learned at. Cross-verified against Wowhead's spell data (g_spells[id]),
# which matched this SQL dump's spell_template row for the same id exactly.
STARTER_RECIPES = {
    3918: 1,  # Rough Blasting Powder (reagent: 1x Rough Stone)
}

# Vanilla profession skill tier breakpoints (no Master tier pre-TBC)
TIERS = [
    (1, 75, "Apprentice"),
    (75, 150, "Journeyman"),
    (150, 200, "Expert"),
    (200, 300, "Artisan"),  # no Master tier pre-TBC; Artisan extends to the 300 cap
]


def tier_for_skill(value):
    for lo, hi, name in TIERS:
        if lo <= value <= hi:
            return name
    return "Unknown"


def extract_table_sql(full_text, table_name):
    marker = f"-- Table structure for table `{table_name}`"
    start = full_text.index(marker)
    next_marker = full_text.find("-- Table structure for table `", start + len(marker))
    section = full_text[start:next_marker if next_marker != -1 else len(full_text)]
    insert_match = re.search(
        r"INSERT INTO `%s` VALUES\s*(.*?);\s*(?:UNLOCK TABLES|/\*!40000)" % re.escape(table_name),
        section,
        re.DOTALL,
    )
    if not insert_match:
        raise ValueError(f"No INSERT found for {table_name}")
    return insert_match.group(1)


def parse_tuples(values_blob):
    """Split a VALUES (...),(...),... blob into lists of raw field strings."""
    tuples = []
    i = 0
    n = len(values_blob)
    while i < n:
        if values_blob[i] == "(":
            depth = 1
            j = i + 1
            fields = []
            field_start = j
            in_quote = False
            while j < n and depth > 0:
                c = values_blob[j]
                if in_quote:
                    if c == "\\":
                        j += 1  # skip escaped char
                    elif c == "'":
                        in_quote = False
                else:
                    if c == "'":
                        in_quote = True
                    elif c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            fields.append(values_blob[field_start:j])
                            break
                    elif c == "," and depth == 1:
                        fields.append(values_blob[field_start:j])
                        field_start = j + 1
                j += 1
            tuples.append([f.strip() for f in fields])
            i = j + 1
        else:
            i += 1
    return tuples


def unquote(field):
    field = field.strip()
    if field == "NULL":
        return None
    if field.startswith("'") and field.endswith("'"):
        return field[1:-1].replace("\\'", "'").replace("''", "'")
    return field


def to_int(field):
    v = unquote(field)
    if v is None:
        return 0
    return int(v)


def main():
    with open(SQL_PATH, "r", encoding="utf-8", errors="replace") as f:
        full_text = f.read()

    print("Parsing npc_trainer...")
    trainer_tuples = parse_tuples(extract_table_sql(full_text, "npc_trainer"))
    # cols: entry, spell, spellcost, reqskill, reqskillvalue, reqlevel, ReqAbility1-3, condition_id
    engineering_taught = {}
    for t in trainer_tuples:
        reqskill = to_int(t[3])
        if reqskill != ENGINEERING_SKILL_LINE:
            continue
        spell_id = to_int(t[1])
        reqskillvalue = to_int(t[4])
        prev = engineering_taught.get(spell_id)
        if prev is None or reqskillvalue < prev:
            engineering_taught[spell_id] = reqskillvalue
    print(f"  Found {len(engineering_taught)} distinct spells taught by Engineering trainers.")

    for spell_id, learned_at in STARTER_RECIPES.items():
        engineering_taught.setdefault(spell_id, learned_at)
    print(f"  Added {len(STARTER_RECIPES)} starter recipe(s) auto-granted on learning the profession.")

    print("Parsing item_template (name lookup)...")
    item_tuples = parse_tuples(extract_table_sql(full_text, "item_template"))
    item_names = {}
    for t in item_tuples:
        entry = to_int(t[0])
        name = unquote(t[3])
        item_names[entry] = name
    print(f"  Loaded {len(item_names)} item names.")

    print("Parsing spell_template (reagents + create-item effect)...")
    spell_tuples = parse_tuples(extract_table_sql(full_text, "spell_template"))
    # 1-based col indices from schema dump -> 0-based
    IDX_ID = 0
    IDX_REAGENT = list(range(42, 50))        # Reagent1..8
    IDX_REAGENT_COUNT = list(range(50, 58))  # ReagentCount1..8
    IDX_EFFECT = [61, 62, 63]                # Effect1..3
    IDX_EFFECT_ITEM_TYPE = [103, 104, 105]   # EffectItemType1..3
    IDX_EFFECT_TRIGGER_SPELL = [109, 110, 111]  # EffectTriggerSpell1..3
    IDX_SPELL_NAME = 119

    spells_by_id = {}
    for t in spell_tuples:
        spell_id = to_int(t[IDX_ID])
        spells_by_id[spell_id] = t

    def find_craft_spell(t):
        """Return the spell tuple that actually has the CREATE_ITEM effect.
        Trainer-taught spells are often a LEARN_SPELL wrapper around the
        real craft spell, so follow EffectTriggerSpell one hop if needed."""
        for eff_idx, item_idx in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
            if to_int(t[eff_idx]) == SPELL_EFFECT_CREATE_ITEM:
                return t
        for eff_idx, trig_idx in zip(IDX_EFFECT, IDX_EFFECT_TRIGGER_SPELL):
            if to_int(t[eff_idx]) == SPELL_EFFECT_LEARN_SPELL:
                triggered_id = to_int(t[trig_idx])
                triggered_t = spells_by_id.get(triggered_id)
                if triggered_t is not None:
                    for eff_idx2, item_idx2 in zip(IDX_EFFECT, IDX_EFFECT_ITEM_TYPE):
                        if to_int(triggered_t[eff_idx2]) == SPELL_EFFECT_CREATE_ITEM:
                            return triggered_t
        return None

    recipes = []
    missing_spell = []
    no_create_item = []
    for spell_id, req_skill_value in engineering_taught.items():
        t = spells_by_id.get(spell_id)
        if t is None:
            missing_spell.append(spell_id)
            continue

        craft_t = find_craft_spell(t)
        if craft_t is None:
            no_create_item.append(spell_id)
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

        is_starter = spell_id in STARTER_RECIPES
        recipes.append({
            "spell_id": spell_id,
            "craft_spell_id": to_int(craft_t[IDX_ID]),
            "spell_name": unquote(t[IDX_SPELL_NAME]),
            "crafted_item_id": crafted_item_id,
            "crafted_item_name": item_names.get(crafted_item_id, f"Unknown Item {crafted_item_id}"),
            "required_skill_value": req_skill_value,
            "skill_tier": tier_for_skill(req_skill_value),
            "reagents": reagents,
            "auto_granted": is_starter,
            "source": "cmangos-classic-db+wowhead-crosscheck" if is_starter else "cmangos-classic-db",
            "confidence": "verified",
        })

    recipes.sort(key=lambda r: r["required_skill_value"])

    out = {
        "profession": "Engineering",
        "skill_line_id": ENGINEERING_SKILL_LINE,
        "recipe_count": len(recipes),
        "recipes": recipes,
    }
    with open("engineering_recipes.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("\n=== SUMMARY ===")
    print(f"Engineering trainer-taught spells found: {len(engineering_taught)}")
    print(f"  -> Resolved to full recipes (reagents + crafted item): {len(recipes)}  [source: cmangos-classic-db, confidence: verified]")
    print(f"  -> Missing from spell_template entirely: {len(missing_spell)}  {missing_spell[:10]}")
    print(f"  -> No CREATE_ITEM effect found (not a craft recipe, e.g. schematics/toys/passives): {len(no_create_item)}  {no_create_item[:10]}")
    print(f"\nRecipes with zero reagents listed (suspicious, worth spot-checking): "
          f"{sum(1 for r in recipes if not r['reagents'])}")

    print("\nTier breakdown:")
    from collections import Counter
    tier_counts = Counter(r["skill_tier"] for r in recipes)
    for tier_name in ["Apprentice", "Journeyman", "Expert", "Artisan", "Unknown"]:
        if tier_counts.get(tier_name):
            print(f"  {tier_name}: {tier_counts[tier_name]}")

    print(f"\nWrote engineering_recipes.json ({len(recipes)} recipes)")


if __name__ == "__main__":
    sys.exit(main())
