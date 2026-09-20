# ReagentRoute visual identity

Reference for keeping any new art (banners, logos, icons) consistent with the
site's theme. Written for both human designers and prompting a local
image-generation model.

## Palette

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0c0a0b` | Page background — near-black |
| `--panel` | `#181415` | Card/panel background — dark charcoal |
| `--border` | `#332829` | Borders, dividers — muted dark red-gray |
| `--text` | `#ece8e7` | Primary text — warm off-white |
| `--text-dim` | `#a79d9e` | Secondary text — warm gray |
| `--accent` | `#b3363a` | Primary accent — blood red |
| `--accent-dim` | `#7a2426` | Secondary/muted accent — darker red |
| `--good` | `#7bbf8a` | Positive values only (money recovered) — muted green |

## Mood

"Moody vampire, but not too crazy." Dark and atmospheric without tipping into
full horror or camp. Think candlelit alchemist's study, not a haunted house.

- Near-black backgrounds, no pure `#000`
- One accent color family (red) — resist the urge to add a second bright hue
- Muted/desaturated over neon or saturated — nothing should glow like a UI
  notification badge
- Sharp, clean shapes over painterly/textured — the site itself is flat and
  minimal, so imagery should match, not clash
- Small warm-white highlights (glass shine, a lit waypoint, a candle) for
  contrast — pure red-on-black everywhere reads flat

## Recurring motifs

- **Potion flask / vial** — the "Reagent" half of the name. Rounded bulb,
  narrow neck, simple stopper/cork.
- **Route / waypoint trail** — the "Route" half. A dashed or dotted path
  with small circular waypoint markers, one marker brighter (the
  destination/current position).
- Fantasy-adjacent but generic: no armor, no weapons, no specific creatures.

## What to avoid (copyright)

Style alone isn't copyrightable, so a "dark gothic fantasy, red and black"
prompt is safe. What's risky is reproducing *specific* protected expression:

- Don't prompt for "World of Warcraft style" or name specific WoW characters,
  creatures, or zones
- Don't try to recreate a specific Blizzard icon or splash-art composition
- Don't include the WoW logo or wordmark
- Original composition in a shared genre (dark fantasy) is fine — copying
  something recognizable is not, regardless of the tool used to make it

## Existing assets (for reference / reuse)

- `webapp/static/favicon.svg` / `logo.svg` — the flask + route mark, hand-coded
- `webapp/static/banner-source.svg` (→ rasterized to `og-banner.png`,
  1200×630) — the current link-preview card
- `webapp/static/icons/*.svg` — profession glyphs from game-icons.net
  (CC BY 3.0, credited in the footer)

## Spec for a generated banner (og:image replacement)

If generating an alternative to `og-banner.png`:

- **Dimensions**: 1200×630px (standard social card ratio, 1.91:1)
- **Format**: PNG (Discord/Twitter/Slack don't reliably render SVG for link
  previews)
- **Safe zone**: keep essential content (title, logo) within the center
  ~1000×550px — some platforms crop edges
- **Contains**: the "ReagentRoute" name legible at thumbnail size, the
  flask+route motif somewhere, and ideally the tagline ("Cheapest path to
  level a WoW Classic profession, priced against live Auction House data")
  though it can be dropped if it hurts legibility
- Save as `webapp/static/og-banner.png` to replace the current one directly
