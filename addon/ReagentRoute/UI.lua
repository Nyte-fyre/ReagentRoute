local ADDON_NAME, RR = ...

-- Small shared styling helpers so Core.lua and Checklist.lua don't each
-- reinvent panel/header/backdrop code, and so the two windows actually
-- look like one addon instead of two independently-styled ones. Loads
-- before both (see the .toc files) so its functions are available to
-- either.
RR.UI = {}

RR.UI.COLOR_ACCENT = { 0.78, 0.16, 0.16 }
local COLOR_BORDER = { 0.30, 0.30, 0.30, 1 }
local COLOR_PANEL_BG = { 0, 0, 0, 0.30 }
local COLOR_HEADER_TEXT = { 1, 0.82, 0 } -- standard WoW gold section-header color

-- A flat, minimal bordered panel used to visually group related controls
-- instead of leaving them floating loose on the frame's bare inset. Uses
-- only the always-available WHITE8x8 stock texture (tinted via color),
-- so it needs no custom art -- BackdropTemplate itself is part of the
-- client's shared FrameXML that Classic Era/TBC both ship (confirmed
-- available live -- see HANDOFF.md).
function RR.UI.Panel(parent)
	local panel = CreateFrame("Frame", nil, parent, "BackdropTemplate")
	panel:SetBackdrop({
		bgFile = "Interface\\Buttons\\WHITE8x8",
		edgeFile = "Interface\\Buttons\\WHITE8x8",
		edgeSize = 1,
	})
	panel:SetBackdropColor(unpack(COLOR_PANEL_BG))
	panel:SetBackdropBorderColor(unpack(COLOR_BORDER))
	return panel
end

-- Small icon + gold label, anchored TOPLEFT into `parent` at (x, y).
-- Returns the header frame so callers can anchor content below it.
function RR.UI.SectionHeader(parent, icon, text, x, y)
	local header = CreateFrame("Frame", nil, parent)
	header:SetPoint("TOPLEFT", x, y)
	header:SetSize(16, 16)

	local tex = header:CreateTexture(nil, "ARTWORK")
	tex:SetAllPoints(header)
	tex:SetTexture(icon)

	local label = parent:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	label:SetPoint("LEFT", tex, "RIGHT", 6, 0)
	label:SetText(text)
	label:SetTextColor(unpack(COLOR_HEADER_TEXT))
	header.label = label

	return header
end

-- Muted helper/description text under a section header.
function RR.UI.HelpText(parent, width)
	local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	fs:SetWidth(width)
	fs:SetJustifyH("LEFT")
	fs:SetWordWrap(true)
	return fs
end

-- The addon's standard window chrome: sizing, movability, Escape-to-
-- close, strata, and a small icon next to the title text (matching the
-- .toc's IconTexture so the window and the AddOn list agree on branding).
function RR.UI.NewWindow(globalName, width, height, title)
	local frame = CreateFrame("Frame", globalName, UIParent, "BasicFrameTemplateWithInset")
	frame:SetSize(width, height)
	frame:SetPoint("CENTER")
	frame:SetMovable(true)
	frame:EnableMouse(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", frame.StartMoving)
	frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
	frame:SetFrameStrata("HIGH")
	frame:Hide()
	tinsert(UISpecialFrames, globalName)

	local icon = frame:CreateTexture(nil, "ARTWORK")
	icon:SetSize(16, 16)
	icon:SetPoint("TOP", 0, -6)
	icon:SetTexture("Interface\\Icons\\INV_Misc_Book_09")

	frame.TitleText = frame.TitleText or frame:CreateFontString(nil, "OVERLAY", "GameFontHeader")
	frame.TitleText:ClearAllPoints()
	frame.TitleText:SetPoint("TOP", icon, "BOTTOM", 0, -2)
	frame.TitleText:SetText(title)

	return frame
end
