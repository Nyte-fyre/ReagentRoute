"""Merge real Orange/Yellow/Green/Grey skill-up thresholds (from Classic
Era client data, SkillLineAbility.dbc via wago.tools build 1.15.9.69722)
into engineering_recipes.json.
"""
import csv
import json

ENGINEERING_SKILL_LINE = "202"

rows = list(csv.DictReader(open("data/SkillLineAbility_classic1x.csv", encoding="utf-8")))
eng_rows = [r for r in rows if r["SkillLine"] == ENGINEERING_SKILL_LINE]
by_spell = {int(r["Spell"]): r for r in eng_rows}

data = json.load(open("data/engineering_recipes.json", encoding="utf-8"))

matched = 0
for r in data["recipes"]:
    row = by_spell.get(r["craft_spell_id"])
    if row is None:
        r["trivial_low"] = None
        r["trivial_high"] = None
        continue
    matched += 1
    low = int(row["TrivialSkillLineRankLow"])
    high = int(row["TrivialSkillLineRankHigh"])
    r["trivial_low"] = low
    r["trivial_high"] = high
    # backfill required_skill_value for non-trainer recipes we couldn't get from npc_trainer
    if r.get("required_skill_value") is None:
        r["required_skill_value"] = 1

with open("data/engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"Matched {matched}/{len(data['recipes'])} recipes with real Orange/Yellow/Green/Grey thresholds")
print(f"Source: Classic Era client data (SkillLineAbility.dbc, build 1.15.9.69722 via wago.tools)")
