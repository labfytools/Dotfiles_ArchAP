-- Capabilities avec cmp si disponible
local capabilities = vim.lsp.protocol.make_client_capabilities()
local ok_cmp, cmp_lsp = pcall(require, "cmp_nvim_lsp")

if ok_cmp then
    capabilities = cmp_lsp.default_capabilities(capabilities)
end

-- Groupe nettoyé à chaque chargement de la configuration
local lsp_attach_group = vim.api.nvim_create_augroup(
    "fy59_lsp_attach",
    { clear = true }
)

-- Keymaps LSP
vim.api.nvim_create_autocmd("LspAttach", {
    group = lsp_attach_group,

    callback = function(args)
        local bufnr = args.buf

        local map = function(lhs, rhs, desc)
            vim.keymap.set("n", lhs, rhs, {
                buffer = bufnr,
                desc = desc,
            })
        end

        map("ld", vim.lsp.buf.definition, "LSP: Go to definition")
        map("lD", vim.lsp.buf.declaration, "LSP: Go to declaration")
        map("lr", vim.lsp.buf.references, "LSP: References")
        map("K", vim.lsp.buf.hover, "LSP: Hover")
        map("<leader>rn", vim.lsp.buf.rename, "LSP: Rename")
        map("<leader>ca", vim.lsp.buf.code_action, "LSP: Code action")
        map("<leader>e", vim.diagnostic.open_float, "LSP: Show diagnostic")

        map("[d", function()
            vim.diagnostic.jump({ count = -1 })
        end, "LSP: Prev diagnostic")

        map("]d", function()
            vim.diagnostic.jump({ count = 1 })
        end, "LSP: Next diagnostic")
    end,
})

-- Configuration des serveurs
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
            diagnostics = {
                globals = { "vim" },
            },
        },
    },
})

vim.lsp.config("clangd", {
    capabilities = capabilities,
    cmd = {
        "clangd",
        "--background-index",
        "--clang-tidy",
    },

    on_attach = function(client)
        client.server_capabilities.semanticTokensProvider = nil
    end,
})

-- Activation des serveurs
vim.lsp.enable({
    "clangd",
    "pyright",
    "bashls",
    "lua_ls",
})

-- rust_analyzer est géré par rustaceanvim
