"""Fix required_skill_value for non-trainer recipes: pull the real
RequiredSkillRank from the schematic item itself (item_template) instead
of the placeholder default of 1.
"""
import json
import sys

sys.path.insert(0, r"C:\Users\bruth\AppData\Local\Temp\claude\C--Users-bruth-OneDrive-Desktop-Claude-Code---AI-Accessable\b8a796f2-d0bb-4540-801b-212238a09c64\scratchpad\classicdb")
from extract_engineering import extract_table_sql, parse_tuples, to_int

with open(r"C:\Users\bruth\AppData\Local\Temp\claude\C--Users-bruth-OneDrive-Desktop-Claude-Code---AI-Accessable\b8a796f2-d0bb-4540-801b-212238a09c64\scratchpad\classicdb\ClassicDB_1_12_1_z2815.sql",
          "r", encoding="utf-8", errors="replace") as f:
    full_text = f.read()

item_tuples = parse_tuples(extract_table_sql(full_text, "item_template"))
required_skill_rank = {to_int(t[0]): to_int(t[16]) for t in item_tuples}

data = json.load(open("data/engineering_recipes.json", encoding="utf-8"))

fixed = 0
for r in data["recipes"]:
    lf = r.get("learned_from")
    if not lf or lf.get("type") != "schematic_item":
        continue
    real_min = required_skill_rank.get(lf["item_id"])
    if real_min:
        r["required_skill_value"] = real_min
        fixed += 1

with open("data/engineering_recipes.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"Fixed required_skill_value for {fixed} non-trainer recipes using real item_template.RequiredSkillRank")
