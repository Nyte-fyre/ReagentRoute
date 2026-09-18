"""Join engineering_recipes.json against TradeSkillMaster's public pricing
CSVs to compute the current reagent cost of every recipe on a given realm.

TSM public data: https://tradeskillmaster.com/public-data
Free, static, no API key/rate limit, updated ~every 3 hours.
"""
import csv
import json
import sys

import requests

TSM_BASE = "https://public-data.tradeskillmaster.com"


def copper_to_gsc(copper):
    copper = round(copper)
    sign = "-" if copper < 0 else ""
    copper = abs(copper)
    gold, rem = divmod(copper, 10000)
    silver, c = divmod(rem, 100)
    return f"{sign}{gold}g {silver}s {c}c"


def fetch_realm_prices(game_type, region_slug, realm_slug):
    url = f"{TSM_BASE}/{game_type}/{region_slug}/realm/{realm_slug}/items.csv"
    resp = requests.get(url, headers={"User-Agent": "ReagentRoute/0.1"})
    resp.raise_for_status()
    text = resp.text
    prices = {}
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        prices[int(row["itemId"])] = {
            "name": row["name"],
            "marketValue": int(row["marketValue"] or 0),
            "minBuyout": int(row["minBuyout"] or 0),
        }
    return prices


def price_recipes_data(data, prices, price_field="minBuyout", gatherable_names=None, vendor_prices=None):
    """Price every recipe's reagents (buy side, via minBuyout) and hedge
    against what crafting it back out recovers. `data` is an already-loaded
    recipes dict (i.e. json.load()'d from a *_recipes.json file).

    `gatherable_names`, if given, is a set of reagent item names the player
    says they can gather themselves (via Herbalism/Mining/Skinning -- see
    data/gatherable_materials.json). When a reagent has no AH price AND its
    name is in that set, it's treated as free (unit cost 0) instead of
    marking the whole recipe price-incomplete: the assumption is you go
    gather it rather than buy it, so a thin/missing AH listing for that
    specific item shouldn't block the recipe from the cost model. Reagents
    priced from real AH data always use that price even if also gatherable
    -- this only fills gaps, it never overrides a real listing.

    `vendor_prices`, if given, is a {item_name: copper} map of reagents
    confirmed sold by an ordinary, always-available vendor (see
    data/vendor_prices.json / scripts/build_vendor_prices.py) -- unlimited
    stock, no reputation/quest gate, sold by many NPCs, not a rare/special
    vendor. Same gap-filling role as gatherable_names: only used when a
    reagent has no AH price. Glass Vials are the clearest case -- Alchemy
    potions need one, but nobody lists a 20-copper vial on the Auction
    House when every reagent vendor sells it, so it was showing up as a
    missing price and blocking otherwise-priceable recipes.

    Net cost only ever subtracts the VENDOR sell price. Vendor sale has
    genuinely unlimited depth at a fixed price, so it's safe to apply to
    every single craft in an expected-value model that may imply crafting
    the same item dozens of times over a skill range.

    The AH price (minBuyout, a real live listing) is surfaced separately
    as `ah_value_single_unit` -- informational only, NOT subtracted from
    net cost. It's only realistic for a unit or two; multiplying it across
    every expected craft would assume you can flood the AH at that price
    with zero market impact, which is false (confirmed empirically: doing
    so produced results like "expect to profit 50,000g leveling this
    profession", which is obvious nonsense). Selling a couple of the nicer
    byproducts on the AH is a real, valid way to offset cost -- it just
    isn't safe to bake into the per-craft math the way vendor price is."""
    gatherable_names = gatherable_names or set()
    vendor_prices = vendor_prices or {}
    priced = []
    missing_price_items = set()
    for r in data["recipes"]:
        total = 0
        complete = True
        reagent_costs = []
        for g in r["reagents"]:
            p = prices.get(g["item_id"])
            gathered = False
            vendor_bought = False
            if p is None or p[price_field] == 0:
                vendor_price = vendor_prices.get(g["item_name"])
                if vendor_price is not None:
                    vendor_bought = True
                    unit_cost = vendor_price
                    total += unit_cost * g["count"]
                elif g["item_name"] in gatherable_names:
                    gathered = True
                    unit_cost = 0
                else:
                    complete = False
                    missing_price_items.add((g["item_id"], g["item_name"]))
                    unit_cost = None
            else:
                unit_cost = p[price_field]
                total += unit_cost * g["count"]
            reagent_costs.append({
                **g, "unit_cost_copper": unit_cost, "gathered": gathered, "vendor_bought": vendor_bought,
            })

        crafted_item_id = r.get("crafted_item_id")
        vendor_sell = r.get("vendor_sell_price") or 0
        # Informational only -- see note above. minBuyout (a real, live
        # listing), not marketValue (a smoothed estimate that can be a
        # fabricated non-zero number for items with zero actual listings --
        # confirmed empirically: e.g. one item showed marketValue=50g with
        # minBuyout=0, i.e. no real listings existed at all).
        ah_single_unit = (prices.get(crafted_item_id) or {}).get("minBuyout", 0) if crafted_item_id else 0
        recovered = vendor_sell

        priced.append({
            "crafted_item_id": crafted_item_id,
            "crafted_item_name": r["crafted_item_name"],
            "craft_spell_id": r.get("craft_spell_id"),
            "required_skill_value": r.get("required_skill_value"),
            "skill_tier": r.get("skill_tier"),
            "acquisition": r.get("acquisition", "trainer"),
            "reagent_costs": reagent_costs,
            "total_cost_copper": total if complete else None,
            "total_cost_display": copper_to_gsc(total) if complete else "incomplete (missing AH price)",
            "recovered_value_copper": recovered,  # vendor only -- see docstring
            "ah_value_single_unit_copper": ah_single_unit,  # informational, not in net cost
            "net_cost_copper": (total - recovered) if complete else None,
            "price_complete": complete,
        })
    return priced, missing_price_items


def price_recipes(recipes_path, prices, price_field="minBuyout"):
    """File-path wrapper around price_recipes_data(), for CLI/script use."""
    data = json.load(open(recipes_path, encoding="utf-8"))
    return price_recipes_data(data, prices, price_field)


if __name__ == "__main__":
    game_type = sys.argv[1] if len(sys.argv) > 1 else "classic"
    region_slug = sys.argv[2] if len(sys.argv) > 2 else "us"
    realm_slug = sys.argv[3] if len(sys.argv) > 3 else "whitemane-horde"

    print(f"Fetching live prices for {game_type}/{region_slug}/{realm_slug}...")
    prices = fetch_realm_prices(game_type, region_slug, realm_slug)
    print(f"  Loaded {len(prices)} item prices.")

    priced, missing = price_recipes("data/engineering_recipes.json", prices)

    complete = [p for p in priced if p["price_complete"]]
    complete.sort(key=lambda p: p["total_cost_copper"])

    print(f"\n{len(complete)}/{len(priced)} recipes fully priced ({len(missing)} distinct reagent items have no AH listing).")
    print("\nCheapest 15 recipes to craft right now:")
    for p in complete[:15]:
        tier = p["skill_tier"] or f"non-trainer/{p['acquisition']}"
        print(f"  {p['total_cost_display']:>14}  {p['crafted_item_name']:<35} ({tier})")

    with open("data/engineering_priced.json", "w", encoding="utf-8") as f:
        json.dump({
            "game_type": game_type, "region_slug": region_slug, "realm_slug": realm_slug,
            "recipes": priced,
        }, f, indent=2)
    print("\nWrote data/engineering_priced.json")
