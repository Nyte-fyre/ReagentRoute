"""Download the raw data sources the extraction scripts need, into
raw_data/ (gitignored -- these are large and regenerable, so they aren't
committed; the derived output in data/*.json is the actual deliverable).

Sources:
  - cmangos/classic-db  (GPL-3.0): full SQL content dump for WoW client
    patch 1.12 (Classic Era). https://github.com/cmangos/classic-db
  - cmangos/tbc-db      (GPL-3.0): full SQL content dump for WoW client
    patch 2.4.3 (TBC, Fury of the Sunwell). https://github.com/cmangos/tbc-db
  - wago.tools: DB2/DBC exports of the actual live client data (skill-up
    thresholds, spell reagents/effects, item-teaches-spell links) for
    specific game builds. https://wago.tools

The wago.tools build numbers are pinned to what the current data/*.json
files were generated against, for reproducibility. Bump them (see the
BUILD_* constants below) to pick up newer client data if a build changes
meaningfully -- check https://wago.tools/builds for the current build of
the "wow_classic_era" (Classic Era) or "wow_anniversary" (TBC Anniversary)
branch.

Usage: python scripts/fetch_data.py [--classic] [--tbc]
       (no flags = fetch both)
"""
import gzip
import os
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA = os.path.join(ROOT, "raw_data")
DATA = os.path.join(ROOT, "data")

BUILD_CLASSIC_ERA = "1.15.9.69722"      # wow_classic_era branch
BUILD_TBC_ANNIVERSARY = "2.5.6.69795"   # wow_anniversary branch

CLASSIC_DB_URL = "https://raw.githubusercontent.com/cmangos/classic-db/master/Full_DB/ClassicDB_1_12_1_z2815.sql.gz"
TBC_DB_URL = "https://raw.githubusercontent.com/cmangos/tbc-db/master/Full_DB/TBCDB_1.11.0_Vengeance_One_A_Cmangos_Story.sql.gz"


def download(url, dest_path, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "ReagentRoute-fetch-data/1.0"})
    print(f"  GET {url}")
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        shutil.copyfileobj(resp, out)
    print(f"    -> {dest_path} ({os.path.getsize(dest_path):,} bytes)")


def gunzip(gz_path, out_path):
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    print(f"    unpacked -> {out_path} ({os.path.getsize(out_path):,} bytes)")


def wago_csv_url(table, build):
    return f"https://wago.tools/db2/{table}/csv?build={build}"


def fetch_classic():
    print("\n=== Classic Era (client patch 1.12) ===")
    os.makedirs(os.path.join(RAW_DATA, "classic"), exist_ok=True)
    gz_path = os.path.join(RAW_DATA, "classic", "ClassicDB.sql.gz")
    sql_path = os.path.join(RAW_DATA, "classic", "ClassicDB.sql")
    download(CLASSIC_DB_URL, gz_path)
    gunzip(gz_path, sql_path)

    print(f"\nFetching SkillLineAbility (build {BUILD_CLASSIC_ERA})...")
    download(wago_csv_url("SkillLineAbility", BUILD_CLASSIC_ERA),
             os.path.join(DATA, "SkillLineAbility_classic1x.csv"),
             headers={"User-Agent": "Mozilla/5.0"})


def fetch_tbc():
    print("\n=== TBC Anniversary (client patch 2.4.3) ===")
    os.makedirs(os.path.join(RAW_DATA, "tbc"), exist_ok=True)
    gz_path = os.path.join(RAW_DATA, "tbc", "TBCDB.sql.gz")
    sql_path = os.path.join(RAW_DATA, "tbc", "TBCDB.sql")
    download(TBC_DB_URL, gz_path)
    gunzip(gz_path, sql_path)

    print(f"\nFetching SpellReagents / SpellEffect / ItemEffect / SkillLineAbility / SpellName (build {BUILD_TBC_ANNIVERSARY})...")
    for table, dest in [
        ("SpellReagents", os.path.join(RAW_DATA, "tbc", "SpellReagents.csv")),
        ("SpellEffect", os.path.join(RAW_DATA, "tbc", "SpellEffect.csv")),
        ("ItemEffect", os.path.join(RAW_DATA, "tbc", "ItemEffect.csv")),
        ("SkillLineAbility", os.path.join(DATA, "SkillLineAbility_tbc.csv")),
        ("SpellName", os.path.join(RAW_DATA, "tbc", "SpellName.csv")),
    ]:
        download(wago_csv_url(table, BUILD_TBC_ANNIVERSARY), dest, headers={"User-Agent": "Mozilla/5.0"})

    # extract_profession_tbc.py's legacy wrapper-spell bridge needs classic-db's
    # spell_template too -- make sure it's present if only --tbc was requested.
    classic_sql = os.path.join(RAW_DATA, "classic", "ClassicDB.sql")
    if not os.path.exists(classic_sql):
        print("\nTBC extraction also needs classic-db (for the legacy LEARN_SPELL bridge) -- fetching it too.")
        fetch_classic()


if __name__ == "__main__":
    os.makedirs(RAW_DATA, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    args = sys.argv[1:]
    do_classic = "--classic" in args or not args
    do_tbc = "--tbc" in args or not args

    if do_classic:
        fetch_classic()
    if do_tbc:
        fetch_tbc()

    print("\nDone. You can now run scripts/extract_profession.py and scripts/extract_profession_tbc.py.")
