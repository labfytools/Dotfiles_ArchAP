vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1

require("neo-tree").setup({
  filesystem = {
    follow_current_file = {
        enable = true,
    },
    hijack_netrw_behavior = "open_default",
  },
  window = {
    position = "left",
    width = 30,
  },
})
