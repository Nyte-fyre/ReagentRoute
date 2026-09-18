"""Download the raw DB2 data WoW Forever extraction needs, into
raw_data/forever/ (gitignored). Unlike Classic/TBC, there is no
community emulator database (cmangos-style) for Forever yet -- it's a
brand new beta (launched within the last day, as of this writing) with
no server-side project mature enough to have published one. Everything
here comes straight from wago.tools' export of the live beta client.

Build is pinned for reproducibility -- check https://wago.tools/builds
for the current build of the "wow_classic_beta" branch (verified to be
Forever's actual client: exact string/item matches to community guides'
described "Campsite Recipes" system, e.g. spell/item ids for "Blueprint:
Fermenter" etc. line up exactly).
"""
import os
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA = os.path.join(ROOT, "raw_data", "forever")

BUILD_FOREVER = "1.60.1.69913"  # wow_classic_beta branch -- bump as newer builds appear

TABLES = ["SpellReagents", "SpellEffect", "ItemEffect", "ItemXItemEffect",
          "SkillLineAbility", "Item", "ItemSparse"]


def download(url, dest_path, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    print(f"  GET {url}")
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        shutil.copyfileobj(resp, out)
    print(f"    -> {dest_path} ({os.path.getsize(dest_path):,} bytes)")


if __name__ == "__main__":
    os.makedirs(RAW_DATA, exist_ok=True)
    print(f"=== WoW Forever beta (build {BUILD_FOREVER}) ===")
    for table in TABLES:
        download(
            f"https://wago.tools/db2/{table}/csv?build={BUILD_FOREVER}",
            os.path.join(RAW_DATA, f"{table}.csv"),
        )
    print("\nDone. You can now run scripts/extract_profession_forever.py.")
