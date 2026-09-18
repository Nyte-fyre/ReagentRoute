# Legacy scripts

These are the original single-profession (Engineering-only) extraction
scripts from early development, kept for provenance/reference. They're
**superseded** by `scripts/extract_profession.py`, which generalizes and
consolidates everything they did (trainer recipes, schematic-item
recipes, acquisition resolution including reference/container/fishing
indirection, and real skill-up thresholds) into one reusable pipeline
that works for any profession.

Run order these scripts originally chained (no longer necessary --
`extract_profession.py` does all of this in one pass):

1. `extract_engineering.py` -- trainer-taught recipes
2. `extract_discovered.py` -- schematic-item-taught recipes
3. `merge_engineering.py` -- merge the two + the manually-verified starter recipe
4. `find_acquisition.py` -- direct vendor/drop/quest lookup
5. `merge_acquisition.py` -- merge acquisition data in
6. `find_acquisition_deep.py` -- deep loot-chain resolution (reference/container/fishing)
7. `merge_deep_acquisition.py` -- merge deep acquisition data in
8. `merge_thresholds.py` -- attach real Orange/Yellow/Green/Grey thresholds
9. `fix_min_skill.py` -- fix the skill floor for non-trainer recipes

They won't run as-is (they reference a session-specific temp path for the
SQL dump) -- they're here for history, not to be executed.
