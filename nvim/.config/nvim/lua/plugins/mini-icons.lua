-- lua/plugins/mini-icons.lua
return {
  "nvim-mini/mini.icons",
  lazy = true,         -- ou enlève lazy si tu veux partout
  opts = {
    -- style = "glyph", -- icônes Nerd Font (par défaut)
    -- style = "ascii", -- si ton terminal n’a pas de Nerd Font
  },
  config = function(_, opts)
    require("mini.icons").setup(opts)
  end,
}

