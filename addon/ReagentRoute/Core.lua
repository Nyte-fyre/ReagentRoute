local ADDON_NAME, RR = ...

local frame = CreateFrame("Frame", "ReagentRouteFrame", UIParent, "BasicFrameTemplateWithInset")
frame:SetSize(420, 410)
frame:SetPoint("CENTER")
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:SetFrameStrata("HIGH")
frame:Hide()
tinsert(UISpecialFrames, "ReagentRouteFrame") -- lets Escape close it like a normal game panel

frame.TitleText = frame.TitleText or frame:CreateFontString(nil, "OVERLAY", "GameFontHeader")
frame.TitleText:SetPoint("TOP", 0, -6)
frame.TitleText:SetText("ReagentRoute Export")

local materialsLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
materialsLabel:SetPoint("TOPLEFT", 16, -32)
materialsLabel:SetWidth(388)
materialsLabel:SetJustifyH("LEFT")
materialsLabel:SetText("Owned materials -- Select All below, Ctrl+C, then paste into ReagentRoute's \"Materials you already own\" box:")

local scrollFrame = CreateFrame("ScrollFrame", "ReagentRouteScrollFrame", frame, "UIPanelScrollFrameTemplate")
scrollFrame:SetPoint("TOPLEFT", materialsLabel, "BOTTOMLEFT", 0, -8)
scrollFrame:SetSize(360, 170)

local editBox = CreateFrame("EditBox", nil, scrollFrame)
editBox:SetMultiLine(true)
editBox:SetFontObject(ChatFontNormal)
editBox:SetWidth(340)
editBox:SetAutoFocus(false)
editBox:SetScript("OnEscapePressed", editBox.ClearFocus)
scrollFrame:SetScrollChild(editBox)

-- A dedicated button rather than relying on click-to-select: WoW's
-- native click-to-place-cursor behavior on an EditBox can run after (and
-- clear) a script-driven HighlightText() from OnMouseUp/OnEditFocusGained,
-- so a plain click doesn't reliably select everything. A Button's OnClick
-- doesn't have that native-widget race.
local selectAllButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
selectAllButton:SetSize(90, 20)
selectAllButton:SetPoint("TOPLEFT", scrollFrame, "BOTTOMLEFT", 0, -6)
selectAllButton:SetText("Select All")
selectAllButton:SetScript("OnClick", function()
	editBox:SetFocus()
	editBox:HighlightText()
end)

local skillLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
skillLabel:SetPoint("TOPLEFT", selectAllButton, "BOTTOMLEFT", 0, -12)
skillLabel:SetWidth(388)
skillLabel:SetJustifyH("LEFT")
skillLabel:SetText("Profession skill -- type the current value into ReagentRoute's \"Start skill\" field:")

local skillText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
skillText:SetPoint("TOPLEFT", skillLabel, "BOTTOMLEFT", 0, -8)
skillText:SetWidth(388)
skillText:SetJustifyH("LEFT")

local function Refresh()
	local counts = RR.ScanOwnedMaterials()
	editBox:SetText(RR.FormatOwnedMaterials(counts))

	local profs = RR.GetProfessionSkills()
	if #profs == 0 then
		skillText:SetText("|cffaaaaaaNo known professions found.|r")
	else
		local lines = {}
		for _, p in ipairs(profs) do
			table.insert(lines, string.format("%s: %d / %d", p.name, p.skill, p.max))
		end
		skillText:SetText(table.concat(lines, "\n"))
	end
end

local refreshButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
refreshButton:SetSize(100, 22)
refreshButton:SetPoint("BOTTOMLEFT", 16, 16)
refreshButton:SetText("Rescan")
refreshButton:SetScript("OnClick", Refresh)

local shoppingListButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
shoppingListButton:SetSize(130, 22)
shoppingListButton:SetPoint("LEFT", refreshButton, "RIGHT", 8, 0)
shoppingListButton:SetText("Shopping List...")
shoppingListButton:SetScript("OnClick", function()
	frame:Hide()
	RR.checklistFrame:Show()
end)

local siteLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
siteLabel:SetPoint("BOTTOMRIGHT", -16, 20)
siteLabel:SetText("reagentroute.onrender.com")

frame:SetScript("OnShow", Refresh)

SLASH_REAGENTROUTE1 = "/reagentroute"
SLASH_REAGENTROUTE2 = "/rr"
SlashCmdList["REAGENTROUTE"] = function(msg)
	if msg and msg:lower():match("^list") then
		frame:Hide()
		RR.checklistFrame:Show()
		return
	end
	if frame:IsShown() then
		frame:Hide()
	else
		frame:Show()
	end
end

RR.frame = frame
