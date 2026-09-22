# Distributing the ReagentRoute addon on CurseForge

Next-steps plan for publishing `addon/ReagentRoute/` publicly. Written
after reading CurseForge's own current support documentation directly
(not from memory) -- see Sources at the bottom. Decisions already made
with the user, not open questions:

- **License: MIT**, scoped to `addon/` only (see `addon/LICENSE`) -- the
  rest of this repo stays all rights reserved. Matches WoW addon
  ecosystem norms; CurseForge itself expects a license selection at
  project creation.
- **Packaging: manual ZIP upload for the first release**, not GitHub
  auto-packaging -- this repo is a monorepo (website + addon together),
  and CurseForge's auto-packager assumes a repo dedicated to just the
  addon. Automation is still on the table later (see "Path to
  automation" below), including splitting `addon/` into its own repo if
  that turns out to be the cleaner way to get there.

## What's already correct (verified against CurseForge's own docs)

- **`.toc` naming.** CurseForge's own support article and Wowpedia's TOC
  format reference (the community doc CurseForge itself links to) agree
  on the current official flavor suffixes: `_Vanilla` for Classic Era,
  `_TBC` for Burning Crusade Classic. Our files
  (`ReagentRoute_Vanilla.toc`, `ReagentRoute_TBC.toc`, both inside a
  folder literally named `ReagentRoute`) already match this exactly --
  "every TOC file needs to start with the addon name used in the parent
  folder," which ours does.
- **`SavedVariables` declared** in both `.toc` files (`ReagentRouteDB`).
- **No WoW Forever `.toc`.** Correct to not have one yet -- Blizzard's
  official flavor-suffix table (checked directly) has no Forever entry,
  and `addon/HANDOFF.md`'s open question #1 (does Forever even allow
  addons) is still unanswered. Don't invent a suffix; wait for either
  Blizzard to add one or the open question to resolve.
- **`## X-License: MIT`** added to both `.toc` files this session, plus a
  placeholder comment for `X-Curse-Project-ID` (some CurseForge tooling
  reads this once a project exists) -- left as a comment, not a live
  directive, since there's no real ID yet.

## What's still needed before submitting

1. **A CurseForge account.** This has to be the user's own action --
   account creation isn't something an agent should do on someone's
   behalf. Sign up / log in at curseforge.com.
2. **A player-facing description.** `addon/HANDOFF.md` is a developer
   handoff document (full of "verified live," open questions, internal
   reasoning) -- not what a player browsing CurseForge should read.
   CurseForge requires a `Summary` (short blurb) and a `Description`
   (longer explanation) and will reject submissions where the
   description "does not sufficiently describe the project." Needs
   drafting: what the addon does (export owned materials/skill to
   reagentroute.onrender.com, import a shopping list as an in-game
   checklist, scan the AH for TBC/Forever pricing), how to use it
   (`/rr`), and that it requires the website to actually compute a plan
   (the addon alone doesn't do the optimization).
3. **A project logo image.** CurseForge wants a "unique icon to identify
   your project by" for the project page -- separate from the in-game
   `IconTexture` (currently a stock Blizzard icon,
   `Interface\Icons\INV_Misc_Book_09`, which is fine in-game but not
   distinctive for a listing page). The website already has a custom
   flask+route logo (`webapp/static/logo.svg`) -- reusing/adapting that
   would keep the addon and website visually consistent. Needs exporting
   to a raster format CurseForge accepts (PNG likely, size TBD -- check
   at submission time).
4. **A changelog for the first release.** CurseForge's file-upload step
   asks for one per file. For a first release this can just summarize
   what's in `addon/HANDOFF.md`'s Status section (P0/P1/P2, what's
   verified where).
5. **Consider bumping the version.** Both `.toc` files still say
   `## Version: 0.1.0` from the initial scaffold, despite P0/P1/P2 all
   being built and verified live since then. Worth deciding on a version
   number before the first public release rather than shipping "0.1.0"
   for genuinely working software -- your call.

## Submission steps (verified against CurseForge's current support docs)

1. Go to `https://authors.curseforge.com/#/projects/create/choose-game`,
   select World of Warcraft.
2. Fill in: Name (must be unique on CurseForge -- "ReagentRoute" may
   already be taken by an unrelated project, have a fallback name ready),
   Summary, Description, Project License (MIT, per above), Class/Main
   category (likely "Data Export" or similar -- pick what fits;
   CurseForge may bounce it back if the category doesn't match), up to 4
   additional categories, Logo Image.
3. Save, move to the Description tab, refine if needed.
4. License tab -- confirm MIT.
5. Skip the "Additional Images" step -- CurseForge's own docs say this is
   required for texture packs/sims projects, not mods/addons.
6. Go to the Files tab and upload the first ZIP (see "Building the ZIP"
   below). Set Release Type to **Alpha** or **Beta**, not Release, for
   the first upload -- `addon/HANDOFF.md`'s own Definition of Done
   sections are honest that TBC Anniversary's AH-capture side and WoW
   Forever entirely are still unverified/untested. CurseForge's Alpha/
   Beta channels exist exactly for "this works but isn't fully proven
   yet" software; don't mark it Release prematurely just to get it in
   front of more users by default.
7. Tag the file with supported game versions (Classic Era, Burning
   Crusade Classic) per CurseForge's Multi-TOC tagging step.
8. Submit. The project enters moderator review ("Under Review") --
   CurseForge's moderators may request changes or reject; this can take
   some real turnaround time, not instant.

## Building the ZIP (manual packaging)

The folder `addon/ReagentRoute/` is already structured exactly right --
zip its *contents* such that the ZIP's top-level entry is a folder named
`ReagentRoute` containing both `.toc` files and all the `.lua` files
directly (not nested inside an extra `addon/` or `ReagentRoute/ReagentRoute/`
level). `LICENSE` can be included or left out of the packaged ZIP (it's
for the repo/CurseForge project page, not something the game client
reads) -- CurseForge's own `.pkgmeta` convention has a `license-output`
option for exactly this if it's ever wanted inside the package.

```bash
cd addon
zip -r ReagentRoute-v0.1.0.zip ReagentRoute -x "*.git*"
```

(Or equivalent via any zip tool -- the requirement is just "top-level
folder named `ReagentRoute`, `.toc`/`.lua` files directly inside it.")

## Path to automation (later, not now)

If/when a `.pkgmeta`-driven GitHub webhook pipeline is worth setting up
(per CurseForge's Automatic Packaging docs: a webhook posts to
`https://www.curseforge.com/api/projects/{projectID}/package?token={token}`
on every push, tagged commits become Alpha/Beta/Release files based on
the tag name), two paths:

1. **Keep the monorepo, scope packaging with `.pkgmeta`.** A `.pkgmeta`
   file at the repo root with `ignore:` entries for everything except
   `addon/ReagentRoute/`, plus a `move-folders` (or `package-as`) entry
   to lift that subfolder to the package root. Untested against our
   layout -- CurseForge's packager is normally used against dedicated
   addon repos, so this needs real trial-and-error against the live
   system, likely via an Alpha-channel test upload first.
2. **Split `addon/` into its own repo**, webhooked directly -- the
   standard, best-supported CurseForge setup, and the option the user
   explicitly said they're open to if it makes automation land faster.
   Trade-off: loses the current single-repo convenience of website and
   addon changes living together (e.g. this session's website changes for
   `ah_scan_csv`/the shopping-list export box were verified against the
   addon's exact contract in the same repo, same commit history).

No strong recommendation between the two yet -- worth revisiting once
there's been at least one real manual release and a sense of how often
new versions will actually ship.

## Other distribution platforms (not investigated this session)

Wago.io is a real, actively-used alternative for Classic-era addon
distribution with its own addon manager. Worth a look once CurseForge
publishing is working, but not researched here -- don't assume its
submission process matches CurseForge's without checking directly,
same standard as everything else in this doc.

## Sources

Read directly this session, not recalled from training data:
- https://support.curseforge.com/support/solutions/articles/9000208605-creating-and-submitting-a-project
- https://support.curseforge.com/support/solutions/articles/9000209856-multi-toc-for-world-of-warcraft-addons
- https://support.curseforge.com/support/solutions/folders/9000194118 (Automatic Packaging, incl. `.pkgmeta` reference)
- https://wowpedia.fandom.com/wiki/TOC_format (linked by CurseForge's own Multi-TOC article as the community reference for interface numbers and flavor suffixes)
