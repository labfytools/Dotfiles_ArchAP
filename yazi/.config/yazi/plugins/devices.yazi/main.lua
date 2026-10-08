--- @since 26.9.1

-- CONTRACT: le service UDisks2/Gio des dotfiles est l'unique source des
-- périphériques et des actions. Aucun point de montage n'est construit ici.
local M = {}
local client = (os.getenv("HOME") or "") .. "/.local/bin/labfy-removable-mediactl"
local devices, spaces, ready = {}, {}, false
local space_cache = {}

local function clean(s) return tostring(s or ""):gsub("[%c]", " ") end
local function name(d) return clean(type(d.display_name) == "string" and d.display_name ~= "" and d.display_name or "Périphérique") end
local function allows(d, action)
	for _, candidate in ipairs(type(d.actions) == "table" and d.actions or {}) do
		if candidate == action then return true end
	end
	return false
end
local function detail(d)
	if d.kind == "mtp" then return "MTP" end
	if not d.mounted then return "Non monté" end
	return spaces[d.runtime_id] and (spaces[d.runtime_id] .. " libres") or "Espace indisponible"
end
local publish = ya.sync(function(_, list, free, ok)
	devices, spaces, ready = list, free, ok
	ui.render()
end)
local function list()
	local output, err = Command(client):arg("list"):output()
	if err or not output or not output.status.success then return nil end
	local ok, state = pcall(ya.json_decode, output.stdout)
	if not ok or type(state) ~= "table" or state.schema ~= "labfy.removable-media" or type(state.devices) ~= "table" then return nil end
	return state.devices
end
local function free_space(path)
	local output, err = Command("df"):arg({ "-B1", "--output=avail", "--", path }):output()
	if err or not output or not output.status.success then return nil end
	local bytes = tonumber(output.stdout:match("\n%s*(%d+)"))
	return bytes and string.format("%.1f GiB", bytes / 1073741824) or nil
end
local function refresh()
	local found = list()
	if not found then publish({}, {}, false); return end
	local free, next_cache, now = {}, {}, ya.time()
	for _, d in ipairs(found) do
		if d.kind == "block" and d.mounted and type(d.mount_point) == "string" and d.mount_point:sub(1, 1) == "/" then
			local previous = space_cache[d.runtime_id]
			local value = previous and previous.path == d.mount_point and now - previous.at < 30 and previous.value or nil
			value = value or free_space(d.mount_point)
			free[d.runtime_id] = value
			next_cache[d.runtime_id] = { path = d.mount_point, at = now, value = value }
		end
	end
	space_cache = next_cache
	publish(found, free, true)
end
local function operate(action, id)
	local output, err = Command(client):arg({ action, id }):output()
	if err or not output or not output.status.success then
		ya.notify { title = "Périphériques", content = clean(output and output.stderr or err or "Échec inconnu"):sub(1, 240), level = "error", timeout = 6 }
		return nil
	end
	local ok, state = pcall(ya.json_decode, output.stdout)
	return ok and type(state) == "table" and state or nil
end
function M:entry()
	local found = list()
	if not found then
		ya.notify { title = "Périphériques", content = "Service indisponible", level = "error", timeout = 5 }
		return
	end
	if #found == 0 then
		ya.notify { title = "Périphériques", content = "Aucun périphérique amovible", timeout = 3 }
		return
	end
	local keys, cands = "123456789abcdefghijklmnopqrstuvwxyz", {}
	for i, d in ipairs(found) do
		if i > #keys then break end
		cands[i] = { on = keys:sub(i, i), desc = name(d) .. " · " .. detail(d) }
	end
	local selected = ya.which { cands = cands }
	local d = selected and found[selected]
	if not d then return end
	local actions = {}
	if d.mounted and allows(d, "open") then
		actions[#actions + 1] = { on = "o", desc = "Ouvrir " .. name(d), action = "open" }
	elseif not d.mounted and allows(d, "mount") then
		actions[#actions + 1] = { on = "m", desc = "Monter puis ouvrir " .. name(d), action = "open" }
	end
	if allows(d, "unmount") then actions[#actions + 1] = { on = "u", desc = "Démonter " .. name(d), action = "unmount" } end
	if allows(d, "safe-remove") then
		actions[#actions + 1] = { on = "e", desc = "Retirer en sécurité " .. name(d), action = "safe-remove" }
	end
	if #actions == 0 then
		ya.notify { title = "Périphériques", content = "Aucune action disponible", level = "warn", timeout = 4 }
		return
	end
	local selected_action = ya.which { cands = actions }
	if not selected_action then return end
	local action = actions[selected_action].action
	if action == "open" and not d.mounted then
		if not ya.confirm { pos = { "center", w = 52, h = 8 }, title = "Montage", body = "Monter " .. name(d) .. " puis ouvrir ?" } then return end
	end
	-- WHY: l'opération « open » du service lance une nouvelle fenêtre Kitty.
	-- Naviguer dans cette instance ; seul le montage passe par le service.
	if action == "open" and d.mounted then
		if type(d.mount_point) == "string" and d.mount_point:sub(1, 1) == "/" then
			ya.emit("cd", { d.mount_point })
		else
			ya.notify { title = "Périphériques", content = "Point de montage indisponible", level = "error", timeout = 5 }
		end
		return
	end
	local result = operate(action == "open" and "mount" or action,
		action == "safe-remove" and d.safe_remove_runtime_id or d.runtime_id)
	if not result then return end
	if action == "open" then
		for _, item in ipairs(result.devices or {}) do
			if item.runtime_id == d.runtime_id and item.mounted and type(item.mount_point) == "string" and item.mount_point:sub(1, 1) == "/" then
				ya.emit("cd", { item.mount_point })
				break
			end
		end
	end
	refresh()
end
function M:setup()
	-- INVARIANT: un seul temporisateur Lua par instance ; pas de lsblk au rendu.
	ya.async(function() while true do refresh(); ya.sleep(5) end end)
	local original_new, original_redraw, original_click = Parent.new, Parent.redraw, Parent.click
	function Parent:new(area, tab)
		local rows = area.w >= 17 and math.min(8, math.floor(area.h / 3)) or 0
		local body = ui.Rect { x = area.x, y = area.y + rows, w = area.w, h = area.h - rows }
		local parent = original_new(self, body, tab)
		parent._devices_header = rows > 0 and ui.Rect { x = area.x, y = area.y, w = area.w, h = rows } or nil
		return parent
	end
	function Parent:redraw()
		local output, area = original_redraw(self), self._devices_header
		if not area then return output end
		local lines = { ui.Line { ui.Span("PÉRIPHÉRIQUES"):fg("#b4befe"):bold() } }
		if not ready then
			lines[#lines + 1] = ui.Line("  État indisponible")
		elseif #devices == 0 then
			lines[#lines + 1] = ui.Line("  Aucun support")
		else
			for _, d in ipairs(devices) do
				if #lines + 2 >= area.h then break end
				local icon = d.kind == "mtp" and "󰄜 " or (d.mounted and "󰋊 " or "󰐑 ")
				lines[#lines + 1] = ui.Line(ui.truncate(icon .. name(d), { max = area.w }))
				lines[#lines + 1] = ui.Line { ui.Span(ui.truncate("   " .. detail(d), { max = area.w })):fg("#a6adc8") }
			end
		end
		lines[#lines + 1] = ui.Line { ui.Span(string.rep("─", math.max(0, area.w - 1))):fg("#585b70") }
		output[#output + 1] = ui.Text(lines):area(area)
		return output
	end
	function Parent:click(event, up)
		local area = self._devices_header
		if area and event.y < area.y + area.h then return end
		return original_click(self, event, up)
	end
end
return M
