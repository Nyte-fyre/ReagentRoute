local ADDON_NAME, RR = ...
local UI = RR.UI

local frame = UI.NewWindow("ReagentRouteFrame", 420, 486, "ReagentRoute")

-- ===== Owned materials panel =====
local matPanel = UI.Panel(frame)
matPanel:SetPoint("TOPLEFT", 14, -44)
matPanel:SetPoint("TOPRIGHT", -14, -44)
matPanel:SetHeight(248)

UI.SectionHeader(matPanel, "Interface\\Icons\\INV_Misc_Bag_08", "Owned Materials", 10, -10)

local matHelp = UI.HelpText(matPanel, 372)
matHelp:SetPoint("TOPLEFT", matPanel, "TOPLEFT", 10, -32)
matHelp:SetText("Click Select All below, Ctrl+C, then paste into ReagentRoute's \"Materials you already own\" box.")

local scrollFrame = CreateFrame("ScrollFrame", "ReagentRouteScrollFrame", matPanel, "UIPanelScrollFrameTemplate")
scrollFrame:SetPoint("TOPLEFT", matHelp, "BOTTOMLEFT", 0, -8)
scrollFrame:SetSize(350, 130)

local editBox = CreateFrame("EditBox", nil, scrollFrame)
editBox:SetMultiLine(true)
editBox:SetFontObject(ChatFontNormal)
editBox:SetWidth(330)
editBox:SetHeight(126)
editBox:SetAutoFocus(false)
editBox:SetScript("OnEscapePressed", editBox.ClearFocus)
scrollFrame:SetScrollChild(editBox)
-- Same click-through fix as the shopping-list paste box (Checklist.lua):
-- clicking the scroll area itself, not just the EditBox's own hit
-- region, should focus it.
scrollFrame:EnableMouse(true)
scrollFrame:SetScript("OnMouseDown", function()
	editBox:SetFocus()
end)

-- A dedicated button rather than relying on click-to-select: WoW's
-- native click-to-place-cursor behavior on an EditBox can run after (and
-- clear) a script-driven HighlightText() from OnMouseUp/OnEditFocusGained,
-- so a plain click doesn't reliably select everything. A Button's OnClick
-- doesn't have that native-widget race.
local selectAllButton = CreateFrame("Button", nil, matPanel, "UIPanelButtonTemplate")
selectAllButton:SetSize(90, 20)
selectAllButton:SetPoint("TOPLEFT", scrollFrame, "BOTTOMLEFT", 0, -8)
selectAllButton:SetText("Select All")
selectAllButton:SetScript("OnClick", function()
	editBox:SetFocus()
	editBox:HighlightText()
end)

local bankStatusText = matPanel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
bankStatusText:SetPoint("LEFT", selectAllButton, "RIGHT", 10, 0)
bankStatusText:SetPoint("RIGHT", matPanel, "RIGHT", -10, 0)
bankStatusText:SetJustifyH("LEFT")
bankStatusText:SetWordWrap(true)

-- ===== Profession skill panel =====
local skillPanel = UI.Panel(frame)
skillPanel:SetPoint("TOPLEFT", matPanel, "BOTTOMLEFT", 0, -10)
skillPanel:SetPoint("TOPRIGHT", matPanel, "BOTTOMRIGHT", 0, -10)
skillPanel:SetHeight(110)

UI.SectionHeader(skillPanel, "Interface\\Icons\\INV_Misc_Note_01", "Profession Skill", 10, -10)

local skillHelp = UI.HelpText(skillPanel, 372)
skillHelp:SetPoint("TOPLEFT", skillPanel, "TOPLEFT", 10, -32)
skillHelp:SetText("Type the current value into ReagentRoute's \"Start skill\" field.")

local skillText = skillPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
skillText:SetPoint("TOPLEFT", skillHelp, "BOTTOMLEFT", 0, -8)
skillText:SetWidth(372)
skillText:SetJustifyH("LEFT")

-- ===== Refresh =====

local function FormatBankStatus()
	local status, ts = RR.GetBankStatus()
	if status == "live" then
		return "|cff40ff40Bank: live|r"
	elseif status == "cached" then
		local age = time() - ts
		local mins = math.floor(age / 60)
		local label
		if mins < 1 then
			label = "just now"
		elseif mins < 60 then
			label = mins .. "m ago"
		else
			label = math.floor(mins / 60) .. "h " .. (mins % 60) .. "m ago"
		end
		return "|cffffcc00Bank: cached " .. label .. " (revisit to refresh)|r"
	end
	return "|cff888888Bank: not visited this session|r"
end

local function Refresh()
	local counts = RR.ScanOwnedMaterials()
	editBox:SetText(RR.FormatOwnedMaterials(counts))
	bankStatusText:SetText(FormatBankStatus())

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

-- ===== Bottom buttons =====

local siteLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
siteLabel:SetPoint("BOTTOMRIGHT", -16, 46)
siteLabel:SetText("reagentroute.onrender.com")

local refreshButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
refreshButton:SetSize(80, 22)
refreshButton:SetPoint("BOTTOMLEFT", 16, 16)
refreshButton:SetText("Rescan")
refreshButton:SetScript("OnClick", Refresh)

local ahButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
ahButton:SetSize(90, 22)
ahButton:SetPoint("LEFT", refreshButton, "RIGHT", 8, 0)
ahButton:SetText("AH Scan...")
ahButton:SetScript("OnClick", function()
	frame:Hide()
	RR.ahFrame:Show()
end)

local shoppingListButton = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
shoppingListButton:SetSize(120, 22)
shoppingListButton:SetPoint("LEFT", ahButton, "RIGHT", 8, 0)
shoppingListButton:SetText("Shopping List...")
shoppingListButton:SetScript("OnClick", function()
	frame:Hide()
	RR.checklistFrame:Show()
end)

frame:SetScript("OnShow", Refresh)

SLASH_REAGENTROUTE1 = "/reagentroute"
SLASH_REAGENTROUTE2 = "/rr"
SlashCmdList["REAGENTROUTE"] = function(msg)
	local sub = msg and msg:lower() or ""
	if sub:match("^list") then
		frame:Hide()
		RR.checklistFrame:Show()
		return
	end
	if sub:match("^ah") then
		frame:Hide()
		RR.ahFrame:Show()
		return
	end
	if frame:IsShown() then
		frame:Hide()
	else
		frame:Show()
	end
end

RR.frame = frame
