local ADDON_NAME, RR = ...

-- Parses "itemID: quantity" lines -- proposed shopping-list export shape
-- (see WEBSITE_HANDOFF.md: not yet implemented on the website side). Same
-- line shape as the owned-materials export for consistency and because
-- it's the simplest thing to produce from build_shopping_list()'s
-- existing item_id/total_count fields. Lines that don't parse cleanly are
-- skipped rather than erroring, same convention as the rest of the addon.
function RR.ParseShoppingList(text)
	local list = {}
	for line in text:gmatch("[^\r\n]+") do
		local idPart, qtyPart = line:match("^%s*(.-)%s*:%s*([%d%.]+)%s*$")
		local itemID = idPart and tonumber(idPart)
		local qty = qtyPart and tonumber(qtyPart)
		if itemID and qty and qty > 0 then
			table.insert(list, { itemID = itemID, needed = qty })
		end
	end
	table.sort(list, function(a, b)
		return a.itemID < b.itemID
	end)
	return list
end
