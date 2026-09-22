local ADDON_NAME, RR = ...
local UI = RR.UI

local frame = UI.NewWindow("ReagentRouteChecklistFrame", 420, 540, "ReagentRoute -- Shopping List")

-- ===== Paste panel =====
local pastePanel = UI.Panel(frame)
pastePanel:SetPoint("TOPLEFT", 14, -44)
pastePanel:SetPoint("TOPRIGHT", -14, -44)
pastePanel:SetHeight(164)

UI.SectionHeader(pastePanel, "Interface\\Icons\\INV_Scroll_03", "Paste Shopping List", 10, -10)

local pasteHelp = UI.HelpText(pastePanel, 372)
pasteHelp:SetPoint("TOPLEFT", pastePanel, "TOPLEFT", 10, -32)
pasteHelp:SetText("Paste the shopping list exported from ReagentRoute, then click Build.")

local pasteScroll = CreateFrame("ScrollFrame", nil, pastePanel, "UIPanelScrollFrameTemplate")
pasteScroll:SetPoint("TOPLEFT", pasteHelp, "BOTTOMLEFT", 0, -8)
pasteScroll:SetSize(350, 56)

local pasteBox = CreateFrame("EditBox", nil, pasteScroll)
pasteBox:SetMultiLine(true)
pasteBox:SetFontObject(ChatFontNormal)
pasteBox:SetWidth(330)
-- Without an explicit height, an empty multi-line EditBox's actual
-- clickable area is only as tall as its (empty) content -- a fraction of
-- the visible scroll area -- so most clicks inside the box fall through
-- to whatever is behind it (the game world, in practice) instead of
-- focusing the box. Found live: typing leaked as WoW hotkeys (toggled
-- nameplates) instead of landing in the box.
pasteBox:SetHeight(52)
pasteBox:SetAutoFocus(false)
pasteBox:SetScript("OnEscapePressed", pasteBox.ClearFocus)
pasteScroll:SetScrollChild(pasteBox)

-- Belt-and-suspenders: clicking anywhere in the scroll area (not just
-- directly on the EditBox's own hit region) should focus it.
pasteScroll:EnableMouse(true)
pasteScroll:SetScript("OnMouseDown", function()
	pasteBox:SetFocus()
end)

local buildButton = CreateFrame("Button", nil, pastePanel, "UIPanelButtonTemplate")
buildButton:SetSize(100, 22)
buildButton:SetPoint("TOPLEFT", pasteScroll, "BOTTOMLEFT", 0, -8)
buildButton:SetText("Build")

local progressText = pastePanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
progressText:SetPoint("LEFT", buildButton, "RIGHT", 12, 0)

-- ===== Results panel =====
local resultsPanel = UI.Panel(frame)
resultsPanel:SetPoint("TOPLEFT", pastePanel, "BOTTOMLEFT", 0, -10)
resultsPanel:SetPoint("TOPRIGHT", pastePanel, "BOTTOMRIGHT", 0, -10)
resultsPanel:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 14, 50)
resultsPanel:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -14, 50)

UI.SectionHeader(resultsPanel, "Interface\\Icons\\Achievement_Quests_Completed", "Checklist", 10, -10)

local listScroll = CreateFrame("ScrollFrame", "ReagentRouteChecklistScroll", resultsPanel, "UIPanelScrollFrameTemplate")
listScroll:SetPoint("TOPLEFT", resultsPanel, "TOPLEFT", 10, -34)
listScroll:SetPoint("BOTTOMRIGHT", resultsPanel, "BOTTOMRIGHT", -28, 10)

local listChild = CreateFrame("Frame", nil, listScroll)
listChild:SetSize(1, 1)
listScroll:SetScrollChild(listChild)

local ROW_HEIGHT = 20
local rows = {}
local currentList = {}

local function GetOrCreateRow(index)
	local row = rows[index]
	if row then
		return row
	end
	row = CreateFrame("Frame", nil, listChild)
	row:SetSize(340, ROW_HEIGHT)
	row:SetPoint("TOPLEFT", 0, -(index - 1) * ROW_HEIGHT)

	-- Faint zebra striping -- readability polish, no custom art needed.
	row.bg = row:CreateTexture(nil, "BACKGROUND")
	row.bg:SetAllPoints(row)
	row.bg:SetTexture("Interface\\Buttons\\WHITE8x8")
	row.bg:SetVertexColor(1, 1, 1, (index % 2 == 0) and 0.04 or 0)

	row.check = row:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	row.check:SetPoint("LEFT", 4, 0)
	row.check:SetWidth(28)

	row.icon = row:CreateTexture(nil, "ARTWORK")
	row.icon:SetSize(16, 16)
	row.icon:SetPoint("LEFT", row.check, "RIGHT", 2, 0)

	row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	row.text:SetPoint("LEFT", row.icon, "RIGHT", 6, 0)
	row.text:SetPoint("RIGHT", -4, 0)
	row.text:SetJustifyH("LEFT")

	rows[index] = row
	return row
end

local function RefreshChecklist()
	if #currentList == 0 then
		progressText:SetText("")
		return
	end
	local owned = RR.ScanOwnedMaterials()
	local doneCount = 0
	for i, entry in ipairs(currentList) do
		local row = GetOrCreateRow(i)
		local have = owned[entry.itemID] or 0
		local satisfied = have >= entry.needed
		if satisfied then
			doneCount = doneCount + 1
		end
		row.check:SetText(satisfied and "|cff40ff40[x]|r" or "|cffff4040[ ]|r")
		-- Item may not be in the client's cache yet if the player has never
		-- seen it -- GetItemInfo returns nil until GET_ITEM_INFO_RECEIVED
		-- fires, which this frame listens for below to refresh once it does.
		local name, _, _, _, _, _, _, _, _, icon = GetItemInfo(entry.itemID)
		row.icon:SetTexture(icon or "Interface\\Icons\\INV_Misc_QuestionMark")
		local label = name or ("Item #" .. entry.itemID)
		local color = satisfied and "|cff40ff40" or "|cffffffff"
		row.text:SetText(string.format("%s%s -- %d / %d|r", color, label, math.min(have, entry.needed), entry.needed))
		row:Show()
	end
	for i = #currentList + 1, #rows do
		rows[i]:Hide()
	end
	listChild:SetSize(340, math.max(1, #currentList * ROW_HEIGHT))
	progressText:SetText(string.format("%d / %d complete", doneCount, #currentList))
end

buildButton:SetScript("OnClick", function()
	currentList = RR.ParseShoppingList(pasteBox:GetText())
	RefreshChecklist()
end)

-- Auto-ticks items off as the player acquires them (BAG_UPDATE) and fills
-- in names/icons once the client finishes caching item data for anything
-- the player hasn't seen before (GET_ITEM_INFO_RECEIVED).
frame:RegisterEvent("BAG_UPDATE")
frame:RegisterEvent("GET_ITEM_INFO_RECEIVED")
frame:SetScript("OnEvent", function(self)
	if self:IsShown() then
		RefreshChecklist()
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

RR.checklistFrame = frame
