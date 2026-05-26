local map = vim.keymap.set
local opts = { noremap = true, silent = true }

-- Recherche
map("n", "<leader>h", "<cmd>nohlsearch<cr>", { desc = "Clear hlsearch" })

-- neo-tree
map("n", "<C-n>", "<cmd>Neotree toggle<CR>", { silent = true, desc = "Explorer" })

local telescope = require("telescope.builtin")

-- Telescope
map("n", "<leader>ff", telescope.find_files, { desc = "Find files" })
map("n", "<leader>fg", telescope.live_grep, { desc = "Live grep" })
map("n", "<leader>fb", telescope.buffers, { desc = "Find buffers" })
map("n", "<leader>fh", telescope.help_tags, { desc = "Find help" })

-- LSP
map("n", "gd", vim.lsp.buf.definition, opts)
map("n", "gr", vim.lsp.buf.references, opts)
map("n", "K", vim.lsp.buf.hover, opts)
map("n", "<leader>rn", vim.lsp.buf.rename, opts)
map("n", "<leader>ca", vim.lsp.buf.code_action, opts)
map("n", "<leader>d", vim.diagnostic.open_float, opts)
map("n", "[d", vim.diagnostic.goto_prev, opts)
map("n", "]d", vim.diagnostic.goto_next, opts)


require("which-key").add({
    -- mappings sans <leader>
    { "<leader>f",  group = "find" },
    { "ff",         "<cmd>Telescope find_files<cr>", desc = "Find files" },
    { "fg",         "<cmd>Telescope live_grep<cr>",  desc = "Live grep" },
    { "fb",         "<cmd>Telescope buffers<cr>",    desc = "Buffers" },
    { "fh",         "<cmd>Telescope help_tags<cr>",  desc = "Help tags" },

    { "w",          group = "write" },
    { "ww",         "<cmd>w<cr>",                    desc = "Write file" },

    -- mappings sous <leader>
    { "<leader>f",  group = "file" },
    { "<leader>ff", "<cmd>Telescope find_files<cr>", desc = "Find files" },
    { "<leader>fg", "<cmd>Telescope live_grep<cr>",  desc = "Live grep" },
})

vim.keymap.set("x", "<Tab>", ">gv", { desc = "Indent selection" })
vim.keymap.set("x", "<S-Tab>", "<gv", { desc = "Unindent selection" })

local function devcontainer()
    local container = vim.fn.getenv("DEVCONTAINER_ID")

    if container == vim.NIL or container == nil or container == "" then
        vim.notify("Aucun DEVCONTAINER_ID trouvé", vim.log.levels.ERROR)
        return nil
    end

    return tostring(container)
end

local function docker_cmd(cmd)
    local container = devcontainer()
    if not container then
        return
    end

    vim.cmd("write")
    vim.cmd("terminal docker exec -it -u vscode " .. container .. " zsh -lc '" .. cmd .. "'")
end

vim.keymap.set("n", "<F5>", function()
    local file = vim.fn.expand("%")
    local out = vim.fn.expand("%:r")

    docker_cmd("gcc -Wall -Wextra -std=c17 -g " .. file .. " -o " .. out)
end, { desc = "GCC compile current file" })

vim.keymap.set("n", "<F6>", function()
    local out = vim.fn.expand("%:r")
    docker_cmd("./" .. out)
end, { desc = "Run current program" })

vim.keymap.set("n", "<F7>", function()
    local out = vim.fn.expand("%:r")
    docker_cmd("gdb ./" .. out)
end, { desc = "Debug with GDB" })

vim.keymap.set("n", "<F8>", function()
    local out = vim.fn.expand("%:r")
    docker_cmd("valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes ./" .. out)
end, { desc = "Run Valgrind" })

vim.keymap.set("n", "<leader>cb", function()
    docker_cmd(
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && cmake --build build --parallel")
end, { desc = "CMake build" })

vim.keymap.set("n", "<leader>cc", function()
    docker_cmd("cmake --build build --target clean")
end, { desc = "CMake clean" })

vim.keymap.set("n", "<leader>cp", function()
    docker_cmd("cppcheck --enable=all --std=c17 --suppress=missingIncludeSystem -I include src")
end, { desc = "Cppcheck project" })
