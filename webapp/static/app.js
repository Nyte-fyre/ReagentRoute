const planForm = document.getElementById("plan-form");
const gameVersionSelect = document.getElementById("game-version");
const versionHint = document.getElementById("version-hint");
const professionSelect = document.getElementById("profession");
const startSkillInput = document.getElementById("start-skill");
const targetSkillInput = document.getElementById("target-skill");
const pricingFields = document.getElementById("pricing-fields");
const realmSelect = document.getElementById("realm-select");
const factionSelect = document.getElementById("faction-select");
const realmHint = document.getElementById("realm-hint");
const ownedTextarea = document.getElementById("owned-materials");
const computeBtn = document.getElementById("compute-btn");
const errorEl = document.getElementById("error");
const resultsPanel = document.getElementById("results-panel");
const loadingEl = document.getElementById("loading");
const resultsEl = document.getElementById("results");
const browseResultsEl = document.getElementById("browse-results");

const PROFESSION_ICONS = {
  Alchemy: "⚗️",
  Blacksmithing: "🔨",
  Cooking: "🍳",
  Enchanting: "✨",
  Engineering: "⚙️",
  "First Aid": "🩹",
  Jewelcrafting: "💎",
  Leatherworking: "🤾",
  Tailoring: "🧵",
};

let gameVersions = {}; // id -> {label, pricing_available}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wowheadLink(itemId, spellId, label) {
  const safeLabel = escapeHtml(label);
  if (itemId) {
    return `<a href="https://www.wowhead.com/classic/item=${itemId}" target="_blank" rel="noopener">${safeLabel}</a>`;
  }
  if (spellId) {
    return `<a href="https://www.wowhead.com/classic/spell=${spellId}" target="_blank" rel="noopener">${safeLabel}</a>`;
  }
  return safeLabel;
}

function friendlyError(rawMessage) {
  if (/404/.test(rawMessage) && /realm/i.test(rawMessage)) {
    return "Couldn't find that realm on TradeSkillMaster. Double-check the slug at tradeskillmaster.com/public-data (case matters, and it usually needs a -horde or -alliance suffix).";
  }
  if (/502/.test(rawMessage) || /Could not fetch prices/i.test(rawMessage)) {
    return "Couldn't reach TradeSkillMaster's price data right now. Try again in a moment.";
  }
  return rawMessage;
}

function parseOwnedMaterials(text) {
  const owned = {};
  text.split("\n").forEach((line) => {
    const idx = line.lastIndexOf(":");
    if (idx === -1) return;
    const name = line.slice(0, idx).trim();
    const qty = parseFloat(line.slice(idx + 1).trim());
    if (name && !Number.isNaN(qty) && qty > 0) owned[name] = qty;
  });
  return owned;
}

function currentVersion() {
  return gameVersions[gameVersionSelect.value] || { pricing_available: true, label: "" };
}

async function loadGameVersions() {
  const res = await fetch("/api/game-versions");
  const versions = await res.json();
  versions.forEach((v) => (gameVersions[v.id] = v));
  gameVersionSelect.innerHTML = versions.map((v) => `<option value="${v.id}">${v.label}</option>`).join("");
  onVersionChange();
}

function onVersionChange() {
  const v = currentVersion();
  pricingFields.classList.toggle("hidden", !v.pricing_available);
  computeBtn.textContent = v.pricing_available ? "Compute plan" : "Browse recipes";
  versionHint.textContent = v.pricing_available
    ? ""
    : "No live Auction House pricing source exists yet for this version -- showing known recipes and reagents only.";
  loadProfessions();
  if (v.pricing_available) loadRealms();
}

async function loadRealms() {
  const res = await fetch(`/api/realms?game_version=${gameVersionSelect.value}`);
  const data = await res.json();

  factionSelect.innerHTML = data.factions.map((f) => `<option value="${f.id}">${f.label}</option>`).join("");

  if (!data.realms.length) {
    realmSelect.innerHTML = `<option value="">No known realms yet</option>`;
    realmSelect.disabled = true;
    realmHint.textContent = "No realm list available for this version yet.";
    return;
  }
  realmSelect.disabled = false;
  realmSelect.innerHTML = data.realms
    .map((r) => `<option value="${r.slug}">${r.label}${r.population ? ` (${r.population} pop)` : ""}</option>`)
    .join("");
  realmHint.innerHTML = `Realm list is a curated, verified sample &mdash; not every realm TSM tracks is listed yet.
    <a href="https://tradeskillmaster.com/public-data" target="_blank" rel="noopener">Full TSM realm list</a>`;
}

async function loadProfessions() {
  const res = await fetch(`/api/professions?game_version=${gameVersionSelect.value}`);
  const professions = await res.json();
  professionSelect.innerHTML = professions
    .map((p) => {
      const icon = PROFESSION_ICONS[p.profession] || "";
      return `<option value="${p.profession}">${icon} ${p.profession} (${p.recipe_count} recipes)</option>`;
    })
    .join("");
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function clearError() {
  errorEl.classList.add("hidden");
  errorEl.textContent = "";
}

async function computePlan(event) {
  if (event) event.preventDefault();
  clearError();
  realmSelect.classList.remove("input-error");

  const version = currentVersion();
  const gameVersion = gameVersionSelect.value;

  if (version.pricing_available) {
    if (!realmSelect.value) {
      showError("No realm selected -- pick one from the list (or this version has none available yet).");
      realmSelect.classList.add("input-error");
      realmSelect.focus();
      return;
    }
  }

  resultsPanel.classList.remove("hidden");
  resultsEl.classList.add("hidden");
  browseResultsEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");
  computeBtn.disabled = true;
  const busyLabel = version.pricing_available ? "Computing…" : "Loading…";
  computeBtn.textContent = busyLabel;
  resultsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    if (version.pricing_available) {
      const payload = {
        profession: professionSelect.value,
        game_version: gameVersion,
        start_skill: parseInt(startSkillInput.value, 10) || 1,
        target_skill: parseInt(targetSkillInput.value, 10) || 300,
        realm: `${realmSelect.value}-${factionSelect.value}`,
        owned_materials: parseOwnedMaterials(ownedTextarea.value),
      };
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      renderResults(await res.json());
    } else {
      const params = new URLSearchParams({ profession: professionSelect.value, game_version: gameVersion });
      const res = await fetch(`/api/recipes?${params}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      const data = await res.json();
      renderBrowseResults(data, parseInt(startSkillInput.value, 10) || 1, parseInt(targetSkillInput.value, 10) || 375);
    }
  } catch (err) {
    showError(friendlyError(err.message));
    if (version.pricing_available) realmSelect.classList.add("input-error");
    resultsPanel.classList.add("hidden");
  } finally {
    loadingEl.classList.add("hidden");
    computeBtn.disabled = false;
    computeBtn.textContent = version.pricing_available ? "Compute plan" : "Browse recipes";
  }
}

function renderResults(data) {
  document.getElementById("gross-cost").textContent = data.gross_reagent_cost_display;
  document.getElementById("recovered-cost").textContent = "-" + data.recovered_from_vendor_display;
  document.getElementById("net-cost").textContent = data.net_market_cost_display;

  const pricedEl = document.getElementById("recipes-priced");
  pricedEl.textContent = `${data.recipes_priced} / ${data.recipes_total}`;
  const coverage = data.recipes_priced / data.recipes_total;
  pricedEl.classList.toggle("stat-value-warn", coverage < 0.7);

  const ownedStat = document.getElementById("owned-stat");
  const costToYouEl = document.getElementById("cost-to-you");
  if (data.value_saved_from_owned_copper > 0) {
    ownedStat.classList.remove("hidden");
    costToYouEl.textContent = data.cost_to_you_display;
  } else {
    ownedStat.classList.add("hidden");
  }

  const leftoverEl = document.getElementById("leftover");
  const leftoverEntries = Object.entries(data.leftover_owned_materials || {});
  if (leftoverEntries.length) {
    leftoverEl.textContent =
      "Unused from what you own: " +
      leftoverEntries.map(([name, qty]) => `${name} (${Math.round(qty * 100) / 100})`).join(", ");
    leftoverEl.classList.remove("hidden");
  } else {
    leftoverEl.classList.add("hidden");
  }

  const gapsEl = document.getElementById("gaps");
  if (data.gaps && data.gaps.length) {
    gapsEl.textContent = `No priced recipe available at ${data.gaps.length} skill point(s) in this range -- plan may have a gap.`;
    gapsEl.classList.remove("hidden");
  } else {
    gapsEl.classList.add("hidden");
  }

  const tbody = document.querySelector("#plan-table tbody");
  tbody.innerHTML = data.plan
    .map((row) => {
      const range = row.skill_from === row.skill_to ? row.skill_from : `${row.skill_from}-${row.skill_to}`;
      const craftLink = wowheadLink(row.crafted_item_id, row.craft_spell_id, row.recipe);
      const ahNote = row.ah_value_single_unit_display
        ? ` <span class="ah-note-inline">(AH: ~${row.ah_value_single_unit_display} for 1)</span>`
        : "";
      const reagentLinks = row.reagents
        .map((g) => `${wowheadLink(g.item_id, null, g.item_name)} &times;${g.count}`)
        .join(", ");
      return `<tr>
        <td>${range}</td>
        <td>${craftLink}${ahNote}</td>
        <td class="reagents-cell">${reagentLinks}</td>
        <td>${row.net_cost_display}</td>
        <td>${row.running_total_display}</td>
      </tr>`;
    })
    .join("");

  resultsEl.classList.remove("hidden");
}

function renderBrowseResults(data, startSkill, targetSkill) {
  const inRange = data.recipes.filter((r) => {
    const skill = r.required_skill_value ?? 1;
    return skill >= startSkill && skill <= targetSkill;
  });

  document.getElementById("browse-note").textContent =
    `${inRange.length} of ${data.recipe_count} known ${data.profession} recipes fall within skill ${startSkill}-${targetSkill}. ` +
    `Reagent lists are verified; exact skill-up odds use the same Orange/Yellow/Green/Grey model as Classic Era.`;

  const tbody = document.querySelector("#browse-table tbody");
  tbody.innerHTML = inRange
    .map((r) => {
      const craftLink = wowheadLink(r.crafted_item_id, r.craft_spell_id, r.crafted_item_name);
      const reagentLinks = r.reagents
        .map((g) => `${wowheadLink(g.item_id, null, g.item_name)} &times;${g.count}`)
        .join(", ");
      const skill = r.required_skill_value ?? "?";
      const acq = r.acquisition_note ? `${r.acquisition} &mdash; ${escapeHtml(r.acquisition_note)}` : r.acquisition;
      return `<tr>
        <td>${skill}</td>
        <td>${craftLink}</td>
        <td class="reagents-cell">${reagentLinks}</td>
        <td class="reagents-cell">${acq}</td>
      </tr>`;
    })
    .join("");

  browseResultsEl.classList.remove("hidden");
}

planForm.addEventListener("submit", computePlan);
gameVersionSelect.addEventListener("change", onVersionChange);
realmSelect.addEventListener("change", () => realmSelect.classList.remove("input-error"));
loadGameVersions();
