return {
  {
    "windwp/nvim-autopairs",
    event = "InsertEnter",
    opts = {
      disable_filetype = { "TelescopePrompt", "vim" },
      -- tu pourras ajuster ici (ignored_next_char, fast_wrap, etc.)
    },
  },
}

