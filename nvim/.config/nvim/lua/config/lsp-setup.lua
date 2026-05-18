local capabilities = vim.lsp.protocol.make_client_capabilities()
local ok_cmp, cmp_lsp = pcall(require, "cmp_nvim_lsp")
if ok_cmp then
  capabilities = cmp_lsp.default_capabilities(capabilities)
end

local lspconfig = require("lspconfig")

-- Fonction appelée quand un serveur LSP se connecte à un buffer
local on_attach = function(_, bufnr)
  local map = function(mode, lhs, rhs, desc)
    vim.keymap.set(mode, lhs, rhs, { buffer = bufnr, desc = desc })
  end

  -- Keymaps de base LSP
  map("n", "gd", vim.lsp.buf.definition, "LSP: Go to definition")
  map("n", "gr", vim.lsp.buf.references, "LSP: References")
  map("n", "K", vim.lsp.buf.hover, "LSP: Hover")
  map("n", "<leader>rn", vim.lsp.buf.rename, "LSP: Rename")
  map("n", "<leader>ca", vim.lsp.buf.code_action, "LSP: Code action")
  map("n", "[d", vim.diagnostic.goto_prev, "LSP: Prev diagnostic")
  map("n", "]d", vim.diagnostic.goto_next, "LSP: Next diagnostic")

  -- Format on save (si le serveur sait formater)
  vim.api.nvim_create_autocmd("BufWritePre", {
    buffer = bufnr,
    callback = function()
      vim.lsp.buf.format({ async = false })
    end,
  })
end

-- Pyright pour Python
-- Exemple approximatif avec la future API
local cfg = vim.lsp._config  -- ou vim.lsp.config selon la version

cfg.setup("pyright", {
  on_attach = on_attach,
  capabilities = capabilities,
})
