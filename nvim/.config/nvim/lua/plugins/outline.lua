-- lua/plugins/outline.lua
return {
  "hedyhli/outline.nvim",
  cmd = { "Outline", "OutlineOpen" },
  keys = {
    { "<leader>o", "<cmd>Outline<cr>", desc = "Toggle outline" },
  },
  opts = {
    outline_window = { position = "right", width = 30 },
  },
}

