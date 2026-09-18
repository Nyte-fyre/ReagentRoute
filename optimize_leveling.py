"""Compute the cheapest expected path to level a Classic profession from
skill A to skill B, personalized against materials the player already owns,
and hedged against what you can sell the crafted item back for (vendor or
AH -- whichever is better).

Skill-up model (verified against cmangos/mangos-classic production server
code, src/game/Entities/Player.cpp UpdateCraftSkill/SkillGainChance):
  Orange (skill < trivial_low):                    100% chance
  Yellow (trivial_low <= skill < midpoint):          75% chance
  Green  (midpoint <= skill < trivial_high):         25% chance
  Grey   (skill >= trivial_high):                     0% chance -- can't skill up
Thresholds (trivial_low/trivial_high) are real per-recipe values from
Classic Era client data (SkillLineAbility.dbc, build 1.15.9.69722).

Net cost per craft = reagent cost - vendor sell price for the item that
craft produces (0 for recipes with no vendor-sellable output, e.g. most
enchants). Only vendor price is subtracted, because it has genuinely
unlimited depth at a fixed price -- safe to apply to every single craft
even when a recipe gets crafted dozens of times over a skill range. AH
value is surfaced separately as informational (ah_value_single_unit) and
NOT subtracted here: it's only realistic for a unit or two, and assuming
you can flood the AH with duplicates at today's quoted price produces
nonsense (verified empirically -- see price_recipes.py).

At each individual skill point, the expected gold cost to advance one
point via a given recipe is (net cost of one craft) / (skill-up
probability), since expected crafts-to-success = 1/p. Because the choice
at each skill point is independent, greedily picking the cheapest
expected *net* cost recipe available at every point is optimal for the
crafting PATH -- it correctly prefers a recipe that's pricier to craft
but resells well over a cheaper one that resells for nothing. Owned
materials don't change which recipes get chosen -- they reduce what the
path actually costs you, applied afterward as a single shared inventory
pool that depletes as the plan consumes it in order.
"""
import json
import sys

CHANCE_ORANGE = 1.00
CHANCE_YELLOW = 0.75
CHANCE_GREEN = 0.25


def skillup_chance(skill, trivial_low, trivial_high):
    if trivial_low is None or trivial_high is None:
        return None
    if skill >= trivial_high:
        return 0.0
    midpoint = (trivial_low + trivial_high) / 2
    if skill >= midpoint:
        return CHANCE_GREEN
    if skill >= trivial_low:
        return CHANCE_YELLOW
    return CHANCE_ORANGE


def copper_to_gsc(copper):
    copper = round(copper)
    sign = "-" if copper < 0 else ""
    copper = abs(copper)
    gold, rem = divmod(copper, 10000)
    silver, c = divmod(rem, 100)
    return f"{sign}{gold}g {silver}s {c}c"


def build_recipe_costs_data(recipes_data, priced_data):
    """Return list of recipes with: min_skill, trivial_low, trivial_high,
    gross cost per craft, recovered value per craft (vendor sell price),
    net cost per craft, item ids (for linking), and the raw reagent list
    (for owned-stock accounting). Both args are already-loaded dicts."""
    recipes = recipes_data["recipes"]
    priced = priced_data["recipes"]
    priced_by_name = {p["crafted_item_name"]: p for p in priced}

    out = []
    for r in recipes:
        if r["trivial_low"] is None or r["required_skill_value"] is None:
            continue
        p = priced_by_name.get(r["crafted_item_name"])
        if p is None or not p["price_complete"]:
            continue

        gross_cost = sum(g["count"] * g["unit_cost_copper"] for g in p["reagent_costs"])
        recovered = p.get("recovered_value_copper", 0)

        out.append({
            "name": r["crafted_item_name"],
            "crafted_item_id": p.get("crafted_item_id"),
            "craft_spell_id": p.get("craft_spell_id"),
            "min_skill": r["required_skill_value"],
            "trivial_low": r["trivial_low"],
            "trivial_high": r["trivial_high"],
            "cost_per_craft": gross_cost,
            "recovered_per_craft": recovered,  # vendor sell price only
            "ah_value_single_unit": p.get("ah_value_single_unit_copper", 0),
            "net_cost_per_craft": gross_cost - recovered,
            "reagents": p["reagent_costs"],  # [{item_id, item_name, count, unit_cost_copper}, ...]
        })
    return out


def build_recipe_costs(recipes_path, priced_path):
    """File-path wrapper around build_recipe_costs_data(), for CLI use."""
    recipes_data = json.load(open(recipes_path, encoding="utf-8"))
    priced_data = json.load(open(priced_path, encoding="utf-8"))
    return build_recipe_costs_data(recipes_data, priced_data)


def optimize(recipes, start_skill, target_skill):
    """Greedy per-skill-point optimizer on NET cost (reagent cost minus
    resale value). Returns (total_net_cost, total_gross_cost,
    total_recovered, plan, gaps). plan is a list of
    (skill_point, recipe_dict, expected_crafts, net_ev_cost, gross_ev_cost)."""
    total_net, total_gross, total_recovered = 0.0, 0.0, 0.0
    plan = []
    gaps = []

    for skill in range(start_skill, target_skill):
        best = None
        best_chance = None
        best_ev = None
        for r in recipes:
            if not (r["min_skill"] <= skill < r["trivial_high"]):
                continue
            chance = skillup_chance(skill, r["trivial_low"], r["trivial_high"])
            if not chance:
                continue
            ev_cost = r["net_cost_per_craft"] / chance
            if best_ev is None or ev_cost < best_ev:
                best_ev = ev_cost
                best = r
                best_chance = chance

        if best is None:
            gaps.append(skill)
            continue

        expected_crafts = 1 / best_chance
        gross_ev = best["cost_per_craft"] * expected_crafts
        recovered_ev = best["recovered_per_craft"] * expected_crafts
        total_net += best_ev
        total_gross += gross_ev
        total_recovered += recovered_ev
        plan.append((skill, best, expected_crafts, best_ev, gross_ev))

    return total_net, total_gross, total_recovered, plan, gaps


def apply_owned_materials(plan, owned_items):
    """Walk the plan in order, depleting a shared owned-materials pool as
    each step's *expected* reagent consumption is subtracted from it.
    Returns (total_value_saved_copper, remaining_stock)."""
    stock = dict(owned_items)
    total_saved = 0.0
    for skill, recipe, expected_crafts, net_ev, gross_ev in plan:
        for g in recipe["reagents"]:
            have = stock.get(g["item_name"], 0)
            if have <= 0:
                continue
            expected_consumed = expected_crafts * g["count"]
            covered = min(have, expected_consumed)
            stock[g["item_name"]] = have - covered
            total_saved += covered * g["unit_cost_copper"]
    return total_saved, stock


def summarize_plan(plan):
    """Collapse consecutive identical recipe choices into ranges, with a
    running tally of net cost for display."""
    if not plan:
        return []
    ranges = []
    start_skill, recipe, _, net_ev, gross_ev = plan[0]
    run_net, run_gross = net_ev, gross_ev
    prev_skill = start_skill
    for skill, recipe2, _, net_ev, gross_ev in plan[1:]:
        if recipe2["name"] == recipe["name"] and skill == prev_skill + 1:
            run_net += net_ev
            run_gross += gross_ev
            prev_skill = skill
            continue
        ranges.append((start_skill, prev_skill, recipe, run_net, run_gross))
        start_skill, recipe, run_net, run_gross = skill, recipe2, net_ev, gross_ev
        prev_skill = skill
    ranges.append((start_skill, prev_skill, recipe, run_net, run_gross))

    running_total = 0.0
    out = []
    for lo, hi, recipe, net_cost, gross_cost in ranges:
        running_total += net_cost
        out.append((lo, hi, recipe, net_cost, gross_cost, running_total))
    return out


if __name__ == "__main__":
    start_skill = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    target_skill = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    owned_path = sys.argv[3] if len(sys.argv) > 3 else None

    recipes = build_recipe_costs("data/engineering_recipes.json", "data/engineering_priced.json")
    print(f"{len(recipes)} recipes usable in cost model (priced + have skill-up thresholds)\n")

    total_net, total_gross, total_recovered, plan, gaps = optimize(recipes, start_skill, target_skill)

    print(f"Cheapest expected-value path: Engineering {start_skill} -> {target_skill}")
    print(f"Gross reagent cost:      {copper_to_gsc(total_gross)}")
    print(f"Recovered (vendor/AH):  -{copper_to_gsc(total_recovered)}")
    print(f"Net spend:               {copper_to_gsc(total_net)}")

    if owned_path:
        owned_items = json.load(open(owned_path, encoding="utf-8"))
        saved, remaining_stock = apply_owned_materials(plan, owned_items)
        print(f"Value of owned materials used: -{copper_to_gsc(saved)}")
        print(f"Cost to you:                    {copper_to_gsc(total_net - saved)}")
        leftover = {k: v for k, v in remaining_stock.items() if v > 0.01}
        if leftover:
            print(f"\nMaterials you own that won't be used on this path: {leftover}")
    print()

    print("Plan (skill range -> recipe -> net cost -> running total):")
    for lo, hi, recipe, net_cost, gross_cost, running in summarize_plan(plan):
        rng = f"{lo}" if lo == hi else f"{lo}-{hi}"
        print(f"  [{rng:>9}] {recipe['name']:<35} {copper_to_gsc(net_cost):>12}   running: {copper_to_gsc(running)}")

    if gaps:
        print(f"\nNo priced/known recipe available at {len(gaps)} skill point(s): {gaps[:20]}{'...' if len(gaps)>20 else ''}")
        print("(these represent gaps in our recipe/price data, not necessarily gaps in the real game)")
