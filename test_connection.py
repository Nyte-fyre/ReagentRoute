"""Verify OAuth2 + Game Data API access against Blizzard's Classic Era API."""
import os
import sys

import requests

REGION = "us"
NAMESPACE = "static-classic1x-us"
LOCALE = "en_US"

TOKEN_URL = "https://us.battle.net/oauth/token"
API_BASE = f"https://{REGION}.api.blizzard.com"


def load_env(path=".env"):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def get_access_token(client_id, client_secret):
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def api_get(path, token, params=None):
    params = dict(params or {})
    params["namespace"] = NAMESPACE
    params["locale"] = LOCALE
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    if not resp.ok:
        print(f"Request failed: GET {path}")
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def main():
    env = load_env()
    client_id = env.get("BLIZZARD_CLIENT_ID")
    client_secret = env.get("BLIZZARD_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Missing BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET in .env")
        sys.exit(1)

    print("Requesting OAuth2 token...")
    token = get_access_token(client_id, client_secret)
    print("Got access token.\n")

    print("Fetching profession index...")
    index = api_get("/data/wow/profession/index", token)
    professions = index.get("professions", [])
    print(f"Found {len(professions)} professions.\n")

    engineering = next(
        (p for p in professions if p["name"].lower() == "engineering"), None
    )
    if not engineering:
        print("Could not find 'Engineering' in profession index. Names returned:")
        for p in professions:
            print(f"  - {p['name']} (id={p['id']})")
        sys.exit(1)

    print(f"Engineering profession id: {engineering['id']}\n")

    print(f"Fetching profession {engineering['id']} details...")
    detail = api_get(f"/data/wow/profession/{engineering['id']}", token)

    tiers = detail.get("skill_tiers", [])
    print(f"\nEngineering has {len(tiers)} skill tiers:")
    for tier in tiers:
        print(f"  - {tier['name']} (id={tier['id']})")


if __name__ == "__main__":
    main()
