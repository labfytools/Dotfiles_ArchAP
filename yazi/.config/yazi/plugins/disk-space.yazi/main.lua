--- @since 26.9.1

-- CONTRACT: « avail » est l'espace disponible pour l'utilisateur courant,
-- contrairement à la capacité totale ; df interroge le filesystem du CWD.
local M = {}
local value, last_path = "Espace indisponible", nil
local publish = ya.sync(function(_, path, display)
	if last_path ~= path then return end
	value = display
	ui.render()
end)
local function human(bytes)
	local units, i = { "B", "KiB", "MiB", "GiB", "TiB", "PiB" }, 1
	while bytes >= 1024 and i < #units do bytes, i = bytes / 1024, i + 1 end
	return i == 1 and string.format("%d B", bytes) or string.format("%.1f %s", bytes, units[i])
end
function M:setup()
	local function load(path)
		last_path, value = path, "Espace indisponible"
		ui.render()
		ya.async(function()
			local output, err = Command("df"):arg({ "-B1", "--output=size,avail", "--", path }):output()
			if err or not output or not output.status.success then return end
			local total, available = output.stdout:match("\n%s*(%d+)%s+(%d+)")
			total, available = tonumber(total), tonumber(available)
			if total and available and total > 0 and available <= total then
				publish(path, human(available) .. " libres / " .. human(total))
			end
		end)
	end
	ps.sub("cd", function() load(tostring(cx.active.current.cwd)) end)
	Status:children_add(function()
		local path = tostring(cx.active.current.cwd)
		if path ~= last_path then load(path) end
		return ui.Line { ui.Span("  " .. value):fg("#b4befe") }
	end, 2800, Status.RIGHT)
end
return M
