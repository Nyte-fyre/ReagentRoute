"""ReagentRoute API: serves profession recipe data for both Classic Era
and TBC Anniversary, and computes the cheapest expected-value leveling
plan against live TSM Auction House prices (Classic Era only -- no live
pricing source exists yet for TBC Anniversary realms, see README), hedged
against vendor resale, and personalized against materials the player
already owns.
"""
import glob
import json
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # so relative "data/..." paths in imported modules resolve

from price_recipes import fetch_realm_prices, price_recipes_data, copper_to_gsc  # noqa: E402
from optimize_leveling import (  # noqa: E402
    build_recipe_costs_data, optimize, apply_owned_materials, summarize_plan,
)

app = FastAPI(title="ReagentRoute API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GAME_VERSIONS = {
    "classic": {
        "suffix": "_recipes.json", "label": "Classic Era", "pricing_available": True, "tsm_game_type": "classic",
        "max_skill": 300, "max_skill_confirmed": True,
    },
    "tbc": {
        "suffix": "_tbc_recipes.json", "label": "TBC Anniversary", "pricing_available": False, "tsm_game_type": None,
        "max_skill": 375, "max_skill_confirmed": True,
    },
    "forever": {
        # No official cap announced yet -- this is the highest required_skill_value actually
        # present in our extracted data (see scripts/extract_profession_forever.py), not a
        # confirmed final number. Recipe discovery is incomplete for this version (see
        # Known limitations in README), so this ceiling will likely rise as more data surfaces.
        "suffix": "_forever_recipes.json", "label": "WoW Forever (beta)", "pricing_available": False, "tsm_game_type": None,
        "max_skill": 325, "max_skill_confirmed": False,
    },
}

# Realms verified to actually return data from TSM's public pricing feed
# (classic) or from population trackers (tbc -- no pricing source exists
# yet, so these aren't TSM-verified, just known-real realm names for when
# one appears). "population" is a rough note, not live data.
REALMS = {
    "classic": [
        {"slug": "whitemane", "label": "Whitemane", "population": "medium"},
        {"slug": "atiesh", "label": "Atiesh", "population": "low"},
        {"slug": "grobbulus", "label": "Grobbulus", "population": "low"},
        {"slug": "remulos", "label": "Remulos", "population": "low"},
        {"slug": "arugal", "label": "Arugal", "population": "low"},
        {"slug": "loatheb", "label": "Loatheb", "population": "low"},
        {"slug": "sulthraze", "label": "Sulthraze", "population": "low"},
    ],
    "tbc": [
        {"slug": "nightslayer", "label": "Nightslayer", "population": None},
        {"slug": "dreamscythe", "label": "Dreamscythe", "population": None},
    ],
    "forever": [],
}
FACTIONS = [{"id": "horde", "label": "Horde"}, {"id": "alliance", "label": "Alliance"}]

# Which reagents (by name) are raw materials gathered via Herbalism/Mining/
# Skinning -- see scripts/build_gatherable_materials.py for how this was
# built and verified (real item class/subclass data, cross-checked against
# our own recipes so crafted intermediates like Cured Hides or bars don't
# get miscounted as raw gathers).
GATHERABLE_MATERIALS = json.load(open(os.path.join(ROOT, "data", "gatherable_materials.json"), encoding="utf-8"))

# Reagents confirmed sold by an ordinary, always-available vendor (see
# scripts/build_vendor_prices.py) -- applied unconditionally to every plan,
# no opt-in checkbox needed, since "this NPC sells it" is a verified fact
# about the game, not a personalization choice like gathering professions.
VENDOR_PRICES = json.load(open(os.path.join(ROOT, "data", "vendor_prices.json"), encoding="utf-8"))
GATHERING_PROFESSIONS = [
    {"id": "herbalism", "label": "Herbalism"},
    {"id": "mining", "label": "Mining"},
    {"id": "skinning", "label": "Skinning"},
]


def recipes_path_for(profession, game_version):
    v = GAME_VERSIONS.get(game_version)
    if v is None:
        raise HTTPException(400, f"Unknown game_version '{game_version}'. Use one of: {list(GAME_VERSIONS)}")
    return os.path.join(ROOT, "data", f"{profession.lower().replace(' ', '_')}{v['suffix']}")


def matches_version(filename, game_version):
    """True if `filename` belongs to `game_version` and not some OTHER
    version whose suffix happens to also match (e.g. '*_recipes.json'
    matching '*_tbc_recipes.json' too, since one is a suffix of the
    other) -- pick the longest/most-specific matching suffix."""
    candidates = [(gv, cfg["suffix"]) for gv, cfg in GAME_VERSIONS.items() if filename.endswith(cfg["suffix"])]
    if not candidates:
        return False
    best_gv, _ = max(candidates, key=lambda pair: len(pair[1]))
    return best_gv == game_version


class PlanRequest(BaseModel):
    profession: str
    game_version: str = "classic"
    start_skill: int = 1
    target_skill: int = 300
    game_type: str = "classic"
    region: str = "us"
    realm: str
    owned_materials: dict[str, float] = {}
    gathering_professions: list[str] = []


@app.get("/api/game-versions")
def list_game_versions():
    return [
        {
            "id": k, "label": v["label"], "pricing_available": v["pricing_available"],
            "max_skill": v["max_skill"], "max_skill_confirmed": v["max_skill_confirmed"],
        }
        for k, v in GAME_VERSIONS.items()
    ]


@app.get("/api/professions")
def list_professions(game_version: str = "classic"):
    if game_version not in GAME_VERSIONS:
        raise HTTPException(400, f"Unknown game_version '{game_version}'. Use one of: {list(GAME_VERSIONS)}")
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "*_recipes.json"))):
        if not matches_version(os.path.basename(path), game_version):
            continue
        d = json.load(open(path, encoding="utf-8"))
        out.append({
            "profession": d["profession"],
            "skill_line_id": d["skill_line_id"],
            "recipe_count": d["recipe_count"],
        })
    return out


@app.get("/api/realms")
def list_realms(game_version: str = "classic"):
    if game_version not in GAME_VERSIONS:
        raise HTTPException(400, f"Unknown game_version '{game_version}'. Use one of: {list(GAME_VERSIONS)}")
    return {"realms": REALMS.get(game_version, []), "factions": FACTIONS}


@app.get("/api/gathering-professions")
def list_gathering_professions():
    return GATHERING_PROFESSIONS


@app.get("/api/recipes")
def list_recipes(profession: str, game_version: str = "tbc"):
    """Raw recipe browser -- no pricing/optimization, just every known
    recipe for a profession with reagents, skill tier, and acquisition.
    Used for game versions with no live pricing source (currently TBC)."""
    recipes_path = recipes_path_for(profession, game_version)
    if not os.path.exists(recipes_path):
        raise HTTPException(404, f"No recipe data for profession '{profession}' ({game_version})")
    data = json.load(open(recipes_path, encoding="utf-8"))
    recipes = sorted(
        data["recipes"],
        key=lambda r: (r["required_skill_value"] is None, r["required_skill_value"] or 0),
    )
    return {
        "profession": data["profession"], "game_version": game_version,
        "recipe_count": len(recipes),
        "recipes": [
            {
                "crafted_item_id": r["crafted_item_id"], "crafted_item_name": r["crafted_item_name"],
                "craft_spell_id": r["craft_spell_id"],
                "required_skill_value": r["required_skill_value"], "skill_tier": r.get("skill_tier"),
                "trivial_low": r.get("trivial_low"), "trivial_high": r.get("trivial_high"),
                "acquisition": r.get("acquisition", "trainer"),
                "acquisition_note": r.get("acquisition_note"),
                "reagents": [
                    {"item_id": g["item_id"], "item_name": g["item_name"], "count": g["count"]}
                    for g in r["reagents"]
                ],
            }
            for r in recipes
        ],
    }


@app.post("/api/plan")
def compute_plan(req: PlanRequest):
    v = GAME_VERSIONS.get(req.game_version)
    if v is None:
        raise HTTPException(400, f"Unknown game_version '{req.game_version}'. Use one of: {list(GAME_VERSIONS)}")
    if not v["pricing_available"]:
        raise HTTPException(
            409,
            f"No live pricing source exists yet for {v['label']}. "
            f"Use GET /api/recipes?profession={req.profession}&game_version={req.game_version} to browse recipes instead.",
        )

    recipes_path = recipes_path_for(req.profession, req.game_version)
    if not os.path.exists(recipes_path):
        raise HTTPException(404, f"No recipe data for profession '{req.profession}'")

    try:
        prices = fetch_realm_prices(req.game_type, req.region, req.realm)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch prices for {req.game_type}/{req.region}/{req.realm}: {e}")

    gatherable_names = set()
    for prof in req.gathering_professions:
        gatherable_names.update(GATHERABLE_MATERIALS.get(prof, []))

    recipes_data = json.load(open(recipes_path, encoding="utf-8"))
    priced, missing = price_recipes_data(
        recipes_data, prices, gatherable_names=gatherable_names, vendor_prices=VENDOR_PRICES
    )
    recipes = build_recipe_costs_data(recipes_data, {"recipes": priced})

    total_net, total_gross, total_recovered, plan, gaps = optimize(recipes, req.start_skill, req.target_skill)

    saved = 0.0
    remaining_stock = {}
    cost_to_you = total_net
    if req.owned_materials:
        saved, remaining_stock = apply_owned_materials(plan, req.owned_materials)
        cost_to_you = total_net - saved

    plan_summary = [
        {
            "skill_from": lo, "skill_to": hi,
            "recipe": recipe["name"],
            "crafted_item_id": recipe["crafted_item_id"],
            "craft_spell_id": recipe["craft_spell_id"],
            "ah_value_single_unit_copper": round(recipe["ah_value_single_unit"]),
            "ah_value_single_unit_display": copper_to_gsc(recipe["ah_value_single_unit"]) if recipe["ah_value_single_unit"] else None,
            "acquisition": recipe.get("acquisition", "trainer"),
            "acquisition_note": recipe.get("acquisition_note"),
            "reagents": [
                {
                    "item_id": g["item_id"], "item_name": g["item_name"], "count": g["count"],
                    "gathered": g.get("gathered", False), "vendor_bought": g.get("vendor_bought", False),
                }
                for g in recipe["reagents"]
            ],
            "net_cost_copper": round(net_cost), "net_cost_display": copper_to_gsc(net_cost),
            "gross_cost_copper": round(gross_cost), "gross_cost_display": copper_to_gsc(gross_cost),
            "running_total_copper": round(running), "running_total_display": copper_to_gsc(running),
        }
        for lo, hi, recipe, net_cost, gross_cost, running in summarize_plan(plan)
    ]

    return {
        "profession": req.profession, "game_version": req.game_version,
        "realm": f"{req.game_type}/{req.region}/{req.realm}",
        "start_skill": req.start_skill, "target_skill": req.target_skill,
        "recipes_priced": sum(1 for p in priced if p["price_complete"]),
        "recipes_total": len(priced),
        "gross_reagent_cost_copper": round(total_gross),
        "gross_reagent_cost_display": copper_to_gsc(total_gross),
        "recovered_from_vendor_copper": round(total_recovered),
        "recovered_from_vendor_display": copper_to_gsc(total_recovered),
        "net_market_cost_copper": round(total_net),
        "net_market_cost_display": copper_to_gsc(total_net),
        "value_saved_from_owned_copper": round(saved),
        "value_saved_from_owned_display": copper_to_gsc(saved) if saved else None,
        "cost_to_you_copper": round(cost_to_you),
        "cost_to_you_display": copper_to_gsc(cost_to_you),
        "leftover_owned_materials": {k: v for k, v in remaining_stock.items() if v > 0.01},
        "plan": plan_summary,
        "gaps": gaps,
    }


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/privacy")
def privacy_page():
    return FileResponse(os.path.join(STATIC_DIR, "privacy.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
