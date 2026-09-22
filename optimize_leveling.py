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
import math
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
            "acquisition": r.get("acquisition", "trainer"),
            "acquisition_note": r.get("acquisition_note"),
            "learned_from": r.get("learned_from"),
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
    Returns (total_value_saved_copper, remaining_stock).

    `owned_items` keys may be either a reagent's exact item_name (what the
    website's free-text textarea produces, for a human typing "Copper Bar:
    40") or its numeric item_id (what the companion addon exports instead,
    since it reads item IDs directly off the client and doesn't have to
    match a display string byte-for-byte). Both key styles are matched
    against the same shared pool so a paste from either source works, and
    a single reagent's demand is only ever covered once even if the pool
    happens to have entries under both its id and its name."""
    stock = {}
    for key, qty in owned_items.items():
        norm_key = int(key) if isinstance(key, str) and key.isdigit() else key
        stock[norm_key] = qty
    total_saved = 0.0
    for skill, recipe, expected_crafts, net_ev, gross_ev in plan:
        for g in recipe["reagents"]:
            remaining = expected_crafts * g["count"]
            for key in (g["item_id"], g["item_name"]):
                if remaining <= 0:
                    break
                have = stock.get(key, 0)
                if have <= 0:
                    continue
                covered = min(have, remaining)
                stock[key] = have - covered
                total_saved += covered * g["unit_cost_copper"]
                remaining -= covered
    return total_saved, stock


AH_CUT_RATE = 0.05  # Blizzard's cut on a successful faction Auction House sale (verified: standard across Classic/TBC)


def apply_ah_hedge(plan, cap):
    """Walk the finalized plan (already chosen using vendor-only net cost
    in optimize() -- this never influences WHICH recipe gets picked, only
    how much extra value gets recovered from what's already being
    crafted) and assume up to `cap` total units of each distinct crafted
    item, summed across the WHOLE plan (not per skill range, not per
    craft), sell on the Auction House at its current minBuyout price
    minus Blizzard's 5% cut. Units beyond the cap get zero additional AH
    recovery -- whatever vendor recovery already applies (if any) is
    already included in net cost and is unaffected.

    This is intentionally bounded: it can never assume unlimited demand
    at one live listing's price, which is exactly what an earlier version
    of this cost model got wrong (produced a nonsensical multi-thousand-
    gold "profit" by naively multiplying a single AH listing's price
    across every expected craft -- see price_recipes.py's docstring).

    Returns (total_ah_recovered_copper, per_skill_detail) where
    per_skill_detail maps skill_point -> (units_sold_on_ah, value_copper),
    for summarize_plan() to fold into the collapsed per-row display."""
    sold_so_far = {}
    total_ah_recovered = 0.0
    per_skill_detail = {}
    for skill, recipe, expected_crafts, net_ev, gross_ev in plan:
        ah_price = recipe.get("ah_value_single_unit") or 0
        if ah_price <= 0 or cap <= 0:
            continue
        name = recipe["name"]
        already = sold_so_far.get(name, 0)
        remaining_cap = max(0, cap - already)
        if remaining_cap <= 0:
            continue
        units = min(expected_crafts, remaining_cap)
        value = units * ah_price * (1 - AH_CUT_RATE)
        total_ah_recovered += value
        sold_so_far[name] = already + units
        per_skill_detail[skill] = (units, value)
    return total_ah_recovered, per_skill_detail


def summarize_plan(plan, ah_detail=None):
    """Collapse consecutive identical recipe choices into ranges, with a
    running tally of net cost for display. If `ah_detail` (from
    apply_ah_hedge()) is given, also sums assumed AH-sold units/value per
    collapsed row for display transparency."""
    if not plan:
        return []
    ah_detail = ah_detail or {}

    def ah_for(skill):
        return ah_detail.get(skill, (0, 0.0))

    ranges = []
    start_skill, recipe, expected_crafts, net_ev, gross_ev = plan[0]
    run_net, run_gross, run_crafts = net_ev, gross_ev, expected_crafts
    run_ah_units, run_ah_value = ah_for(start_skill)
    prev_skill = start_skill
    for skill, recipe2, expected_crafts, net_ev, gross_ev in plan[1:]:
        ah_units, ah_value = ah_for(skill)
        if recipe2["name"] == recipe["name"] and skill == prev_skill + 1:
            run_net += net_ev
            run_gross += gross_ev
            run_crafts += expected_crafts
            run_ah_units += ah_units
            run_ah_value += ah_value
            prev_skill = skill
            continue
        ranges.append((start_skill, prev_skill, recipe, run_net, run_gross, run_crafts, run_ah_units, run_ah_value))
        start_skill, recipe, run_net, run_gross, run_crafts = skill, recipe2, net_ev, gross_ev, expected_crafts
        run_ah_units, run_ah_value = ah_units, ah_value
        prev_skill = skill
    ranges.append((start_skill, prev_skill, recipe, run_net, run_gross, run_crafts, run_ah_units, run_ah_value))

    running_total = 0.0
    out = []
    for lo, hi, recipe, net_cost, gross_cost, expected_crafts, ah_units, ah_value in ranges:
        running_total += net_cost
        out.append((lo, hi, recipe, net_cost, gross_cost, running_total, expected_crafts, ah_units, ah_value))
    return out


def build_shopping_list(plan):
    """Aggregate every reagent across the WHOLE plan into one consolidated
    list -- the basis for both the on-page quantity breakdown and any
    shopping-list export. Quantities are rounded UP (ceil): the
    expected-value math is fractional (e.g. 1.33 crafts), but a real
    shopping list needs a whole number of items to actually go buy, and
    rounding down would leave you short. Returns a list of dicts sorted
    by total cost descending (most expensive reagent first), each with
    item_id, item_name, total_count, unit_cost_copper, total_cost_copper,
    gathered, and vendor_bought (true only if EVERY unit of that item
    across the whole plan came from a gather/vendor source, for display
    purposes -- a mixed reagent, e.g. partly AH-priced and partly
    vendor-priced across different recipes, shows as neither)."""
    totals = {}
    for skill, recipe, expected_crafts, net_ev, gross_ev in plan:
        for g in recipe["reagents"]:
            key = g["item_name"]
            entry = totals.setdefault(key, {
                "item_id": g["item_id"], "item_name": g["item_name"],
                "raw_count": 0.0, "unit_cost_copper": g["unit_cost_copper"] or 0,
                "gathered": True, "vendor_bought": True,
            })
            entry["raw_count"] += expected_crafts * g["count"]
            entry["gathered"] = entry["gathered"] and bool(g.get("gathered"))
            entry["vendor_bought"] = entry["vendor_bought"] and bool(g.get("vendor_bought"))

    out = []
    for entry in totals.values():
        total_count = math.ceil(entry["raw_count"] - 1e-9)  # tolerance for float accumulation
        out.append({
            "item_id": entry["item_id"], "item_name": entry["item_name"],
            "total_count": total_count, "unit_cost_copper": entry["unit_cost_copper"],
            "total_cost_copper": total_count * entry["unit_cost_copper"],
            "gathered": entry["gathered"], "vendor_bought": entry["vendor_bought"],
        })
    out.sort(key=lambda e: e["total_cost_copper"], reverse=True)
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
    for lo, hi, recipe, net_cost, gross_cost, running, expected_crafts, ah_units, ah_value in summarize_plan(plan):
        rng = f"{lo}" if lo == hi else f"{lo}-{hi}"
        print(f"  [{rng:>9}] {recipe['name']:<35} {copper_to_gsc(net_cost):>12}   running: {copper_to_gsc(running)}")

    if gaps:
        print(f"\nNo priced/known recipe available at {len(gaps)} skill point(s): {gaps[:20]}{'...' if len(gaps)>20 else ''}")
        print("(these represent gaps in our recipe/price data, not necessarily gaps in the real game)")
