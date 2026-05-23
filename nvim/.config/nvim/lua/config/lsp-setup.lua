-- capabilities avec cmp si disponible
local capabilities = vim.lsp.protocol.make_client_capabilities()
local ok_cmp, cmp_lsp = pcall(require, "cmp_nvim_lsp")
if ok_cmp then
    capabilities = cmp_lsp.default_capabilities(capabilities)
end

-- Keymaps + format on save (déclenché à chaque attach LSP)
vim.api.nvim_create_autocmd("LspAttach", {
    callback = function(args)
        local bufnr = args.buf
        local map = function(lhs, rhs, desc)
            vim.keymap.set("n", lhs, rhs, { buffer = bufnr, desc = desc })
        end

        map("ld", vim.lsp.buf.definition, "LSP: Go to definition")
        map("lD", vim.lsp.buf.declaration, "LSP: Go to declaration")
        map("lr", vim.lsp.buf.references, "LSP: References")
        map("K", vim.lsp.buf.hover, "LSP: Hover")
        map("<leader>rn", vim.lsp.buf.rename, "LSP: Rename")
        map("<leader>ca", vim.lsp.buf.code_action, "LSP: Code action")
        map("<leader>e", vim.diagnostic.open_float, "LSP: Show diagnostic")
        -- diagnostics dépréciés en 0.11 → remplacés par vim.diagnostic.jump
        map("[d", function() vim.diagnostic.jump({ count = -1 }) end, "LSP: Prev diagnostic")
        map("]d", function() vim.diagnostic.jump({ count = 1 }) end, "LSP: Next diagnostic")

        -- Format on save
        -- vim.api.nvim_create_autocmd("BufWritePre", {
        --    buffer = bufnr,
        --    callback = function()
        --        vim.lsp.buf.format({ async = false })
        --    end,
        -- })
        vim.api.nvim_create_autocmd("BufWritePre", {
            callback = function()
                local ft = vim.bo.filetype
                if ft == "c" or ft == "cpp" then
                    return
                end

                vim.lsp.buf.format({ async = false })
            end,
        })
    end,
})

-- Config des serveurs via la nouvelle API vim.lsp.config
vim.lsp.config("pyright", {
    capabilities = capabilities,
})

vim.lsp.config("bashls", {
    capabilities = capabilities,
})

vim.lsp.config("lua_ls", {
    capabilities = capabilities,
    settings = {
        Lua = {
            diagnostics = { globals = { "vim" } },
        },
    },
})

vim.lsp.config("clangd", {
    cmd = { "clangd", "--background-index", "--clang-tidy" },

    on_attach = function(client, bufnr)
        client.server_capabilities.semanticTokensProvider = nil
    end,
})

-- Activation des serveurs
vim.lsp.enable({ "clangd", "pyright", "bashls", "lua_ls" })

-- rust_analyzer géré par rustaceanvim, ne pas l'activer ici
