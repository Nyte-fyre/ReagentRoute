local ADDON_NAME, RR = ...

local frame = CreateFrame("Frame", "ReagentRouteChecklistFrame", UIParent, "BasicFrameTemplateWithInset")
frame:SetSize(420, 480)
frame:SetPoint("CENTER")
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:SetFrameStrata("HIGH")
frame:Hide()
tinsert(UISpecialFrames, "ReagentRouteChecklistFrame")

frame.TitleText = frame.TitleText or frame:CreateFontString(nil, "OVERLAY", "GameFontHeader")
frame.TitleText:SetPoint("TOP", 0, -6)
frame.TitleText:SetText("ReagentRoute Shopping List")

local pasteLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
pasteLabel:SetPoint("TOPLEFT", 16, -32)
pasteLabel:SetWidth(388)
pasteLabel:SetJustifyH("LEFT")
pasteLabel:SetText("Paste the shopping list exported from ReagentRoute, then click Build:")

local pasteScroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
pasteScroll:SetPoint("TOPLEFT", pasteLabel, "BOTTOMLEFT", 0, -8)
pasteScroll:SetSize(360, 60)

local pasteBox = CreateFrame("EditBox", nil, pasteScroll)
pasteBox:SetMultiLine(true)
pasteBox:SetFontObject(ChatFontNormal)
pasteBox:SetWidth(340)
pasteBox:SetAutoFocus(false)
pasteBox:SetScript("OnEscapePressed", pasteBox.ClearFocus)
pasteScroll:SetScrollChild(pasteBox)

local buildButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
buildButton:SetSize(100, 22)
buildButton:SetPoint("TOPLEFT", pasteScroll, "BOTTOMLEFT", 0, -8)
buildButton:SetText("Build")

local progressText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
progressText:SetPoint("LEFT", buildButton, "RIGHT", 12, 0)

local listScroll = CreateFrame("ScrollFrame", "ReagentRouteChecklistScroll", frame, "UIPanelScrollFrameTemplate")
listScroll:SetPoint("TOPLEFT", buildButton, "BOTTOMLEFT", 0, -12)
listScroll:SetPoint("BOTTOMRIGHT", -34, 16)

local listChild = CreateFrame("Frame", nil, listScroll)
listChild:SetSize(360, 1)
listScroll:SetScrollChild(listChild)

local ROW_HEIGHT = 18
local rows = {}
local currentList = {}

local function GetOrCreateRow(index)
	local row = rows[index]
	if row then
		return row
	end
	row = CreateFrame("Frame", nil, listChild)
	row:SetSize(360, ROW_HEIGHT)
	row:SetPoint("TOPLEFT", 0, -(index - 1) * ROW_HEIGHT)

	row.check = row:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	row.check:SetPoint("LEFT", 0, 0)
	row.check:SetWidth(28)

	row.icon = row:CreateTexture(nil, "ARTWORK")
	row.icon:SetSize(14, 14)
	row.icon:SetPoint("LEFT", row.check, "RIGHT", 2, 0)

	row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	row.text:SetPoint("LEFT", row.icon, "RIGHT", 4, 0)
	row.text:SetPoint("RIGHT", 0, 0)
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
	listChild:SetHeight(math.max(1, #currentList * ROW_HEIGHT))
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

RR.checklistFrame = frame
