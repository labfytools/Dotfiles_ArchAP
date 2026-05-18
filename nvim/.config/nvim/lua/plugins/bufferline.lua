return {
  {
    "akinsho/bufferline.nvim",
    version = "*",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
      options = {
        mode = "buffers",
        separator_style = "slant",
        diagnostics = "nvim_lsp",
        show_buffer_close_icons = true,
        show_close_icon = false,
        always_show_bufferline = true,
        tab_size = 18,
        max_name_length = 22,
        truncate_names = true,
        offsets = {},
        buffer_close_icon = "", 
        diagnostics_indicator = function(count, level, diagnostics_dict, context)
          local s = " "
          for e, n in pairs(diagnostics_dict) do
            local sym = (e == "error" and " ")
              or (e == "warning" and " ")
              or " "
            s = s .. n .. sym
          end
          return s
        end,
      },
    },
  },
}

