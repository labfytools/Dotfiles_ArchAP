-- WHY: le thème de l'éditeur suit la révision Appearance, sans minuterie ni
-- dépendance envers le processus QuickShell.
local M = {}
local uv = vim.uv
local path = (vim.env.XDG_STATE_HOME or (vim.env.HOME .. "/.local/state"))
  .. "/labfy-appearance/effective.json"
local revision = -1
local watcher

local function state()
  local file = io.open(path, "r")
  if not file then return nil end
  local data = file:read("*a")
  file:close()
  local ok, value = pcall(vim.json.decode, data)
  if not ok or type(value) ~= "table" then return nil end
  local flavors = { latte = true, frappe = true, macchiato = true, mocha = true }
  if not flavors[value.effectiveFlavor] or type(value.revision) ~= "number"
      or value.revision < 0 or value.revision % 1 ~= 0
      or type(value.effectiveHighContrast) ~= "boolean" then return nil end
  return value
end

local function apply()
  local current = state()
  local flavor = current and current.effectiveFlavor or "mocha"
  local current_revision = current and current.revision or -1
  if current_revision == revision and vim.g.colors_name == "catppuccin-" .. flavor then return end
  -- CONTRACT: erreurs de l'état ou du plugin n'empêchent pas l'éditeur de démarrer.
  local ok = pcall(function()
    require("catppuccin").setup({
      flavour = flavor,
      dim_inactive = { enabled = false },
      custom_highlights = function(colors)
        if not (current and current.effectiveHighContrast) then return {} end
        return {
          Visual = { bg = colors.surface2, fg = colors.text },
          Search = { bg = colors.yellow, fg = colors.base },
          IncSearch = { bg = colors.peach, fg = colors.base },
          StatusLine = { bg = colors.surface2, fg = colors.text },
          WinSeparator = { fg = colors.overlay2 },
        }
      end,
    })
    vim.cmd.colorscheme("catppuccin-" .. flavor)
  end)
  if not ok then pcall(vim.cmd.colorscheme, "default") end
  revision = current_revision
end

function M.start()
  apply()
  -- fs_event sur le répertoire observe l'écriture tmp + rename atomique.
  -- Un seul handle par instance ; VimLeavePre ferme explicitement sa ressource.
  watcher = uv.new_fs_event()
  if watcher then
    local directory = vim.fn.fnamemodify(path, ":h")
    if uv.fs_stat(directory) then
      local ok = watcher:start(directory, {}, function(err, filename)
        if not err and filename == "effective.json" then vim.schedule(apply) end
      end)
      if not ok then watcher:close(); watcher = nil end
    else watcher:close(); watcher = nil end
  end
  vim.api.nvim_create_autocmd("VimLeavePre", { callback = function()
    if watcher then watcher:stop(); watcher:close(); watcher = nil end
  end })
end

return M
