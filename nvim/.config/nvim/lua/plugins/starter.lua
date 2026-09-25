return {
  {
    "nvim-mini/mini.starter",
    version = false,
    config = function()
      local starter = require("mini.starter")

      starter.setup({
        autoopen = true,
        header = table.concat({
          "███╗   ██╗███████╗ ██████╗ ██╗   ██╗██╗███╗   ███╗",
          "████╗  ██║██╔════╝██╔═══██╗██║   ██║██║████╗ ████║",
          "██╔██╗ ██║█████╗  ██║   ██║██║   ██║██║██╔████╔██║",
          "██║╚██╗██║██╔══╝  ██║   ██║╚██╗ ██╔╝██║██║╚██╔╝██║",
          "██║ ╚████║███████╗╚██████╔╝ ╚████╔╝ ██║██║ ╚═╝ ██║",
          "",
          "##############################################################",
          "####                  FY59's nvim config                  ####",
          "##############################################################",
          "",
        }, "\n"),
        items = {
          starter.sections.recent_files(8),
          starter.sections.telescope(),
          {
            name = "Open Nvim config",
            action = "edit ~/.config/nvim/init.lua",
            section = "Config",
          },
          {
            name = "Quit",
            action = "quit",
            section = "Actions",
          },
        },
        footer = "Happy editing – from FY59's config",
      })
    end,
  },
}
