---@type LazySpec
return {
  {
    "MeanderingProgrammer/render-markdown.nvim",
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      "nvim-tree/nvim-web-devicons", -- ou mini.icons si tu utilises mini
    },
    opts = {
      -- preset = "lazy", -- tu peux tester ce preset plus tard
      enabled = true,
      file_types = { "markdown" },
    },
  },
}
