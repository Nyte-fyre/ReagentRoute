local ADDON_NAME, RR = ...

-- Confirmed empirically 2026-09-22 (Classic Era, /dump C_AuctionHouse,
-- QueryAuctionItems, GetAuctionItemInfo): C_AuctionHouse is nil on this
-- client, QueryAuctionItems/GetAuctionItemInfo are real functions -- this
-- is the legacy (pre-Shadowlands) Auction House API, not the modern
-- C_AuctionHouse namespace. Not yet independently re-confirmed on TBC
-- Anniversary, but both clients share the same underlying Classic-era
-- FrameXML for the AH, so it's expected to match.

ReagentRouteDB = ReagentRouteDB or {}

local function RealmKey()
	local realm = GetRealmName() or "UnknownRealm"
	local faction = UnitFactionGroup("player") or "Neutral"
	return realm .. "-" .. faction
end

local function GetScanTable()
	ReagentRouteDB.ahScans = ReagentRouteDB.ahScans or {}
	local key = RealmKey()
	ReagentRouteDB.ahScans[key] = ReagentRouteDB.ahScans[key] or { items = {} }
	return ReagentRouteDB.ahScans[key]
end
RR.GetAHScanTable = GetScanTable

-- Purely reactive -- this never calls QueryAuctionItems() itself. It only
-- reads whatever's already on screen after the PLAYER runs a search (or
-- clicks Get All, where available). Addons automating AH queries the
-- player didn't request is exactly the kind of "automating game actions"
-- HANDOFF.md's ToS section already rules out for this addon; every
-- capture here is triggered by AUCTION_ITEM_LIST_UPDATE, which only fires
-- in response to a search the player already ran through the normal UI.
local function CaptureCurrentPage()
	local scan = GetScanTable()
	local n = GetNumAuctionItems("list")
	local captured = 0
	for i = 1, (n or 0) do
		local name, _, count, _, _, _, _, _, _, buyoutPrice = GetAuctionItemInfo("list", i)
		local link = GetAuctionItemLink("list", i)
		-- Bid-only listings (buyoutPrice == 0) aren't a usable price --
		-- same reasoning as README.md's caution against treating anything
		-- but a real, live buyout as a pricing basis.
		if link and buyoutPrice and buyoutPrice > 0 and count and count > 0 then
			local itemID = tonumber(link:match("item:(%d+):"))
			if itemID then
				local unitBuyout = math.floor(buyoutPrice / count)
				local existing = scan.items[itemID]
				if not existing or unitBuyout < existing.minBuyout then
					scan.items[itemID] = { name = name, minBuyout = unitBuyout, lastSeen = time() }
				else
					existing.lastSeen = time()
				end
				captured = captured + 1
			end
		end
	end
	scan.lastUpdated = time()
	return captured
end
RR.CaptureAHPage = CaptureCurrentPage

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("AUCTION_ITEM_LIST_UPDATE")
watcher:SetScript("OnEvent", function()
	if AuctionFrame and AuctionFrame:IsShown() then
		CaptureCurrentPage()
	end
end)

-- Count of distinct items captured for the current realm+faction, plus
-- when the scan was last updated (nil if nothing captured yet).
function RR.GetAHScanStatus()
	local scan = GetScanTable()
	local count = 0
	for _ in pairs(scan.items) do
		count = count + 1
	end
	return count, scan.lastUpdated
end

function RR.ClearAHScan()
	GetScanTable().items = {}
end

-- CSV matching the columns price_recipes.py's fetch_realm_prices()
-- actually reads (verified against its source before building this:
-- itemId, name, marketValue, minBuyout -- it never parses "recent",
-- "historical", or "updatedAt" even though TSM's own feed has them, so
-- this export doesn't invent those columns). marketValue is set equal to
-- minBuyout rather than fabricating a smoothed estimate from a handful of
-- live snapshots -- see README.md's own caution that TSM's marketValue
-- can already be a non-zero, unreliable number even when no real listings
-- exist; inventing a second unreliable estimate would make that worse,
-- not better.
function RR.FormatAHScanCSV()
	local scan = GetScanTable()
	local ids = {}
	for itemID in pairs(scan.items) do
		table.insert(ids, itemID)
	end
	table.sort(ids)
	local lines = { "itemId,name,marketValue,minBuyout" }
	for _, itemID in ipairs(ids) do
		local e = scan.items[itemID]
		local escapedName = '"' .. (e.name or ""):gsub('"', '""') .. '"'
		table.insert(lines, string.format("%d,%s,%d,%d", itemID, escapedName, e.minBuyout, e.minBuyout))
	end
	return table.concat(lines, "\n")
end
