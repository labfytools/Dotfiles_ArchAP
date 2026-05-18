local map = vim.keymap.set

-- Recherche
map("n", "<leader>h", "<cmd>nohlsearch<cr>", { desc = "Clear hlsearch" })

-- neo-tree
vim.keymap.set("n", "<C-n>", "<cmd>Neotree toggle<CR>", { silent = true, desc = "Explorer" })

local telescope = require("telescope.builtin")

-- Fuzzy find files
vim.keymap.set("n", "<leader>ff", telescope.find_files, { desc = "Find files" })

-- Live grep
vim.keymap.set("n", "<leader>fg", telescope.live_grep, { desc = "Live grep" })

-- Buffers
vim.keymap.set("n", "<leader>fb", telescope.buffers, { desc = "Find buffers" })

-- Help tags
vim.keymap.set("n", "<leader>fh", telescope.help_tags, { desc = "Find help" })

-- LSP
vim.keymap.set("n", "gd", vim.lsp.buf.definition, opts)
vim.keymap.set("n", "gr", vim.lsp.buf.references, opts)
vim.keymap.set("n", "K", vim.lsp.buf.hover, opts)
vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, opts)
vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action, opts)
vim.keymap.set("n", "<leader>d", vim.diagnostic.open_float, opts)
vim.keymap.set("n", "[d", vim.diagnostic.goto_prev, opts)
vim.keymap.set("n", "]d", vim.diagnostic.goto_next, opts)

-- Indenter en mode Visuel avec Tab / Shift-Tab
vim.keymap.set("v", "<Tab>", ">gv", { desc = "Indent selection" })
vim.keymap.set("v", "<S-Tab>", "<gv", { desc = "Unindent selection" })

require("which-key").add({
  -- mappings sans <leader>
    { "f",  group = "find" },
    { "ff", "<cmd>Telescope find_files<cr>", desc = "Find files" },
    { "fg", "<cmd>Telescope live_grep<cr>",  desc = "Live grep" },
    { "fb", "<cmd>Telescope buffers<cr>",    desc = "Buffers" },
    { "fh", "<cmd>Telescope help_tags<cr>",  desc = "Help tags" },

    { "w",  group = "write" },
    { "ww", "<cmd>w<cr>", desc = "Write file" },

    -- mappings sous <leader>
    { "<leader>f",  group = "file" },
    { "<leader>ff", "<cmd>Telescope find_files<cr>", desc = "Find files" },
    { "<leader>fg", "<cmd>Telescope live_grep<cr>",  desc = "Live grep" },

    --Git
    { "<leader>g", group = "Git"}, 
    { "<leader>gs", "<cmd>Git status<cr>",  desc = "Git status" },
    { "<leader>ga", "<cmd>Git add .<cr>",   desc = "Git add all" },
    { "<leader>gc", "<cmd>Git commit<cr>",  desc = "Git commit" },
    { "<leader>gp", "<cmd>Git push<cr>",    desc = "Git push" },

})

