return {
    -- Mason
    {
        "mason-org/mason.nvim",
        opts = {},
    },

    -- Bridge Mason <-> lspconfig
    {
        "mason-org/mason-lspconfig.nvim",
        opts = {
            ensure_installed = {
                "pyright", -- Python (tu l'avais déjà)
                "bashls",  -- Bash
                "lua_ls",  -- Lua
                -- rust_analyzer : géré par rustaceanvim, pas ici
            },
            automatic_enable = {
                exclude = { "rust_analyzer" },
            },
        },
        dependencies = {
            { "mason-org/mason.nvim", opts = {} },
            "neovim/nvim-lspconfig",
        },
    },

    -- nvim-lspconfig : chargé, config dans lsp-setup.lua
    {
        "neovim/nvim-lspconfig",
        config = function()
            require("config.lsp-setup")
        end,
    },

    -- Rust : rustaceanvim
    {
        "mrcjkb/rustaceanvim",
        version = "^5",
        lazy = false,
    },
}
