return {
  {
    "nvim-telescope/telescope-file-browser.nvim",
    dependencies = {
      "nvim-telescope/telescope.nvim",
      "nvim-lua/plenary.nvim",
    },
    config = function()
      local telescope = require("telescope")

      telescope.setup({
        extensions = {
          file_browser = {
            hijack_netrw = true,
            hidden = { file_browser = true, folder_browser = true },
          },
        },
      })

      telescope.load_extension("file_browser")

      vim.keymap.set("n", "<leader>e", function()
        telescope.extensions.file_browser.file_browser({
          path = vim.loop.cwd(),
          select_buffer = true,
        })
      end, { desc = "File browser" })
    end,
  },
}

