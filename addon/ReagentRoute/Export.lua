local ADDON_NAME, RR = ...

-- Container API differs between client builds: newer ones expose
-- C_Container.*, older ones only the global GetContainerNumSlots /
-- GetContainerItemInfo functions. Detect once and use whichever exists
-- rather than assuming -- see HANDOFF.md's caution about this.
local function GetNumSlots(bag)
	if C_Container and C_Container.GetContainerNumSlots then
		return C_Container.GetContainerNumSlots(bag)
	end
	return GetContainerNumSlots(bag)
end

local function GetSlotItemIDAndCount(bag, slot)
	if C_Container and C_Container.GetContainerItemInfo then
		local info = C_Container.GetContainerItemInfo(bag, slot)
		if not info or not info.itemID then
			return nil
		end
		return info.itemID, info.stackCount or 1
	end
	local _, itemCount, _, _, _, _, itemLink = GetContainerItemInfo(bag, slot)
	if not itemLink then
		return nil
	end
	local itemID = tonumber(itemLink:match("item:(%d+):"))
	if not itemID then
		return nil
	end
	return itemID, itemCount or 1
end

local function ScanBags(bagList)
	local counts = {}
	for _, bag in ipairs(bagList) do
		local slots = GetNumSlots(bag)
		if slots then
			for slot = 1, slots do
				local itemID, count = GetSlotItemIDAndCount(bag, slot)
				if itemID then
					counts[itemID] = (counts[itemID] or 0) + count
				end
			end
		end
	end
	return counts
end

local BANK_BAGS = { BANK_CONTAINER or -1 }
for i = 1, (NUM_BANKBAGSLOTS or 6) do
	table.insert(BANK_BAGS, 4 + i)
end

-- The bank's container contents are only readable through the client API
-- while the bank frame is actually open -- there is no way to query them
-- otherwise, a hard client restriction, not an addon choice. So bank
-- materials only count toward owned-materials while the player is
-- standing at the bank *unless* we snapshot them into SavedVariables the
-- last time the bank was open and fall back to that snapshot otherwise
-- (same technique Bagnon/Altoholic-style addons use). ReagentRouteDB is
-- declared in both .toc files' `## SavedVariables:` line.
ReagentRouteDB = ReagentRouteDB or {}

local function SnapshotBank()
	ReagentRouteDB.bankSnapshot = ScanBags(BANK_BAGS)
	ReagentRouteDB.bankSnapshotTime = time()
end

local bankWatcher = CreateFrame("Frame")
bankWatcher:RegisterEvent("BANKFRAME_OPENED")
bankWatcher:RegisterEvent("BANKFRAME_CLOSED")
bankWatcher:SetScript("OnEvent", function(_, event)
	if event == "BANKFRAME_OPENED" then
		SnapshotBank()
		bankWatcher:RegisterEvent("BAG_UPDATE") -- keeps the snapshot current across a deposit/withdraw without waiting for close+reopen
	elseif event == "BANKFRAME_CLOSED" then
		SnapshotBank() -- final snapshot while the data is still readable
		bankWatcher:UnregisterEvent("BAG_UPDATE")
	else -- BAG_UPDATE, only registered while the bank is open
		SnapshotBank()
	end
end)

-- Reports whether the returned owned-materials totals include LIVE bank
-- data, a CACHED snapshot from a previous bank visit (with its age), or
-- no bank data at all -- surfaced in the UI so a stale snapshot is never
-- silently presented as current (same "don't trust it, check it"
-- standard the rest of this project holds itself to, see README.md).
function RR.GetBankStatus()
	local isLive = BankFrame and BankFrame:IsShown()
	if isLive then
		return "live", nil
	end
	if ReagentRouteDB.bankSnapshotTime then
		return "cached", ReagentRouteDB.bankSnapshotTime
	end
	return "none", nil
end

-- Scans player bags, plus the bank: live if the bank frame is currently
-- open, otherwise falling back to the last cached snapshot (see above).
-- Aggregates by item ID rather than display name -- the website's
-- owned-materials matching used to require an exact item_name string
-- match, which silently zeroed out credit on any whitespace/locale
-- mismatch (see HANDOFF.md's Data contract section). Matching by ID
-- sidesteps that entirely, and item IDs are free to read here (no need
-- to wait on GetItemInfo's async item cache the way a name lookup would).
function RR.ScanOwnedMaterials()
	local counts = ScanBags({ 0, 1, 2, 3, 4 })
	local status = RR.GetBankStatus()
	local bankCounts
	if status == "live" then
		bankCounts = ScanBags(BANK_BAGS)
	elseif status == "cached" then
		bankCounts = ReagentRouteDB.bankSnapshot
	end
	if bankCounts then
		for itemID, count in pairs(bankCounts) do
			counts[itemID] = (counts[itemID] or 0) + count
		end
	end
	return counts
end

-- "itemID: quantity" per line, sorted by item ID for a stable, diffable
-- export. This is the same "key: quantity" shape the website's
-- parseOwnedMaterials() already accepts for human-typed item names --
-- optimize_leveling.apply_owned_materials() on the backend now matches a
-- reagent's item_id first, falling back to item_name, so this pastes
-- straight into the site's existing "Materials you already own" textarea
-- with no website changes needed.
function RR.FormatOwnedMaterials(counts)
	local ids = {}
	for itemID in pairs(counts) do
		table.insert(ids, itemID)
	end
	table.sort(ids)
	local lines = {}
	for _, itemID in ipairs(ids) do
		table.insert(lines, itemID .. ": " .. counts[itemID])
	end
	return table.concat(lines, "\n")
end

-- Every profession the player currently knows, with current/max skill.
-- GetProfessions() returns up to six slot indices (two primary
-- professions, plus secondary ones like fishing/cooking/first aid on
-- client versions that report them this way); nil slots are skipped.
function RR.GetProfessionSkills()
	local out = {}
	local slots = { GetProfessions() }
	for _, index in ipairs(slots) do
		if index then
			local name, _, skillLevel, maxSkillLevel = GetProfessionInfo(index)
			if name then
				table.insert(out, { name = name, skill = skillLevel, max = maxSkillLevel })
			end
		end
	end
	return out
end
