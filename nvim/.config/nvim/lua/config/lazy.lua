-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not (vim.uv or vim.loop).fs_stat(lazypath) then
  local lazyrepo = "https://github.com/folke/lazy.nvim.git"
  local out = vim.fn.system({ "git", "clone", "--filter=blob:none", "--branch=stable", lazyrepo, lazypath })
  if vim.v.shell_error ~= 0 then
    vim.api.nvim_echo({
      { "Failed to clone lazy.nvim:\n", "ErrorMsg" },
      { out, "WarningMsg" },
      { "\nPress any key to exit..." },
    }, true, {})
    vim.fn.getchar()
    os.exit(1)
  end
end
vim.opt.rtp:prepend(lazypath)

-- Make sure to setup `mapleader` and `maplocalleader` before
-- loading lazy.nvim so that mappings are correct.
-- This is also a good place to setup other settings (vim.opt)
vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

-- Setup lazy.nvim
require("lazy").setup({
  spec = {
    -- import your plugins
    { import = "plugins" },
  },
  -- Configure any other settings here. See the documentation for more details.
  -- colorscheme that will be used when installing plugins.
  install = { colorscheme = { "habamax" } },
  -- automatically check for plugin updates
  checker = { enabled = false },
})
local lazy_update_group =
    vim.api.nvim_create_augroup("LazyAutoUpdate", { clear = true })

-- Fermer l'interface lorsque la mise à jour est terminée
vim.api.nvim_create_autocmd("User", {
    group = lazy_update_group,
    pattern = "LazyUpdate",
    once = true,
    callback = function()
        vim.schedule(function()
            local ok, view = pcall(require, "lazy.view")

            if ok and view.view and view.visible() then
                view.view:close()
            end
        end)
    end,
})

-- Lancer la mise à jour à l'ouverture de Neovim
vim.api.nvim_create_autocmd("VimEnter", {
    group = lazy_update_group,
    once = true,
    callback = function()
        vim.schedule(function()
            require("lazy").update({
                show = true,
            })
        end)
    end,
})
