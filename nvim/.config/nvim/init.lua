-- Leader
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- Options de base
local o = vim.opt

o.number = true
o.relativenumber = true
o.termguicolors = true
o.cursorline = true

o.expandtab = true
o.shiftwidth = 4
o.tabstop = 4
o.smartindent = true

o.ignorecase = true
o.smartcase = true

o.wrap = false
o.scrolloff = 5
o.signcolumn = "yes"

vim.opt.clipboard = "unnamedplus"

vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1

-- Avant require("config.lazy")
local ts_site = vim.fn.stdpath("data") .. "/site"
if not vim.tbl_contains(vim.opt.rtp:get(), ts_site) then
  vim.opt.rtp:append(ts_site)
end
-- charge lazy.nvim + plugins
require("config.lazy")
-- Position du curser
vim.api.nvim_create_autocmd("BufReadPost", {
  callback = function()
    local mark = vim.api.nvim_buf_get_mark(0, '"')
    local line_count = vim.api.nvim_buf_line_count(0)
    if mark[1] > 0 and mark[1] <= line_count then
      vim.api.nvim_win_set_cursor(0, mark)
    end
  end,
})

-- Undo persistant
local undodir = vim.fn.stdpath("state") .. "/undo"
if vim.fn.isdirectory(undodir) == 0 then
  vim.fn.mkdir(undodir, "p")
end
vim.opt.undodir = undodir
vim.opt.undofile = true

vim.filetype.add({
  pattern = { [".*/hypr/.*%.conf"] = "hyprlang" },
})

-- require
-- Keymaps (fichier séparé)
require("config.maps")

-- Appel de .md config
require("config.markdown")

-- Mason/LSP
require("mason-lspconfig").setup()

 
vim.cmd.colorscheme "catppuccin-mocha"


