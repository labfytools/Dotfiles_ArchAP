return {
  {
    "echasnovski/mini.map",
    branch = "stable",
    config = function()
      local map = require("mini.map")

      map.setup({
        symbols = {
          encode = map.gen_encode_symbols.dot("4x2"),
        },
        integrations = {
          map.gen_integration.builtin_search(),
          map.gen_integration.diagnostic(),
          map.gen_integration.gitsigns(),
        },
      })

      -- PAS d'ouverture auto : bloc autocmd commenté

      -- <leader>p : toggle minimap
      vim.keymap.set("n", "<leader>p", function()
        map.toggle()
      end, {
        desc = "Toggle minimap",
      })
    end,
  },
}

