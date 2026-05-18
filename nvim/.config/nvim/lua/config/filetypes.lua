local ts = require("nvim-treesitter.parsers")
ts.filetype_to_parsername.swayconfig = "i3"

vim.filetype.add({
  pattern = {
    [".*/sway/config.*"] = "swayconfig",
  },
})
