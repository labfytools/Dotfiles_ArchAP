return {
  "nvim-treesitter/nvim-treesitter",
  build = ":TSUpdate",
  opts = {
    ensure_installed = {
      "bash",
      "c",
      "lua",
      "vim",
      "vimdoc",
      "markdown",
      "markdown_inline",
      "query",
      "python",
      "html",
    },
    auto_install = true,
    highlight = {
      enable = true,
      additional_vim_regex_highlighting = {},
    },
    indent = {
      enable = true,
    },
  },
}

