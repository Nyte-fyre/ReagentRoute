local ADDON_NAME, RR = ...
local UI = RR.UI

local frame = UI.NewWindow("ReagentRouteAHFrame", 420, 430, "ReagentRoute -- AH Scan")

-- ===== Status panel =====
local statusPanel = UI.Panel(frame)
statusPanel:SetPoint("TOPLEFT", 14, -44)
statusPanel:SetPoint("TOPRIGHT", -14, -44)
statusPanel:SetHeight(90)

UI.SectionHeader(statusPanel, "Interface\\Icons\\INV_Misc_Coin_02", "Auction Scan", 10, -10)

local statusHelp = UI.HelpText(statusPanel, 372)
statusHelp:SetPoint("TOPLEFT", statusPanel, "TOPLEFT", 10, -32)
statusHelp:SetText(
	"Open the Auction House and search (or click Get All, where available) -- ReagentRoute records buyout prices from whatever results appear. This never searches on its own."
)

local statusText = statusPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
statusText:SetPoint("TOPLEFT", statusHelp, "BOTTOMLEFT", 0, -8)
statusText:SetWidth(372)
statusText:SetJustifyH("LEFT")

-- ===== Export panel =====
local exportPanel = UI.Panel(frame)
exportPanel:SetPoint("TOPLEFT", statusPanel, "BOTTOMLEFT", 0, -10)
exportPanel:SetPoint("TOPRIGHT", statusPanel, "BOTTOMRIGHT", 0, -10)
exportPanel:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 14, 50)
exportPanel:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -14, 50)

UI.SectionHeader(exportPanel, "Interface\\Icons\\INV_Scroll_03", "Export CSV", 10, -10)

local exportHelp = UI.HelpText(exportPanel, 372)
exportHelp:SetPoint("TOPLEFT", exportPanel, "TOPLEFT", 10, -32)
exportHelp:SetText("Select All below, Ctrl+C, then send this to whoever runs ReagentRoute's TBC/Forever pricing.")

local exportScroll = CreateFrame("ScrollFrame", nil, exportPanel, "UIPanelScrollFrameTemplate")
exportScroll:SetPoint("TOPLEFT", exportHelp, "BOTTOMLEFT", 0, -8)
exportScroll:SetPoint("BOTTOMRIGHT", exportPanel, "BOTTOMRIGHT", -28, 36)

local exportBox = CreateFrame("EditBox", nil, exportScroll)
exportBox:SetMultiLine(true)
exportBox:SetFontObject(ChatFontSmall)
exportBox:SetWidth(330)
exportBox:SetAutoFocus(false)
exportBox:SetScript("OnEscapePressed", exportBox.ClearFocus)
exportScroll:SetScrollChild(exportBox)
exportScroll:EnableMouse(true)
exportScroll:SetScript("OnMouseDown", function()
	exportBox:SetFocus()
end)

local selectAllButton = CreateFrame("Button", nil, exportPanel, "UIPanelButtonTemplate")
selectAllButton:SetSize(90, 20)
selectAllButton:SetPoint("BOTTOMLEFT", exportPanel, "BOTTOMLEFT", 10, 8)
selectAllButton:SetText("Select All")
selectAllButton:SetScript("OnClick", function()
	exportBox:SetFocus()
	exportBox:HighlightText()
end)

local clearButton = CreateFrame("Button", nil, exportPanel, "UIPanelButtonTemplate")
clearButton:SetSize(110, 20)
clearButton:SetPoint("LEFT", selectAllButton, "RIGHT", 8, 0)
clearButton:SetText("Clear Scan")

-- ===== Refresh =====

local function FormatAge(ts)
	if not ts then
		return nil
	end
	local mins = math.floor((time() - ts) / 60)
	if mins < 1 then
		return "just now"
	elseif mins < 60 then
		return mins .. "m ago"
	end
	return math.floor(mins / 60) .. "h " .. (mins % 60) .. "m ago"
end

local function Refresh()
	local count, lastUpdated = RR.GetAHScanStatus()
	if count == 0 then
		statusText:SetText("|cff888888No items captured yet for this realm.|r")
	else
		statusText:SetText(string.format("|cff40ff40%d item%s captured|r -- last updated %s", count, count == 1 and "" or "s", FormatAge(lastUpdated) or "?"))
	end
	exportBox:SetText(RR.FormatAHScanCSV())
end

clearButton:SetScript("OnClick", function()
	RR.ClearAHScan()
	Refresh()
end)

frame:SetScript("OnShow", Refresh)

-- Live-refresh the displayed status/export while this window is open and
-- the player runs another AH search, same pattern Checklist.lua uses for
-- BAG_UPDATE -- no extra scanning happens here, AHScan.lua's own watcher
-- already captured the data; this just re-renders what's now cached.
frame:RegisterEvent("AUCTION_ITEM_LIST_UPDATE")
frame:SetScript("OnEvent", function(self)
	if self:IsShown() then
		Refresh()
	end
end)

-- ===== Bottom buttons =====

local backButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
backButton:SetSize(100, 22)
backButton:SetPoint("BOTTOMLEFT", 16, 16)
backButton:SetText("< Back")
backButton:SetScript("OnClick", function()
	frame:Hide()
	RR.frame:Show()
end)

local siteLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
siteLabel:SetPoint("BOTTOMRIGHT", -16, 22)
siteLabel:SetText("reagentroute.onrender.com")

RR.ahFrame = frame
