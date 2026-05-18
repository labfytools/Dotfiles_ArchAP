# Neovim config – minimal, modulaire, orienté dev

Config Neovim from scratch, en **Lua**, avec [lazy.nvim](https://github.com/folke/lazy.nvim) comme gestionnaire de plugins.  
Objectif : un setup léger, lisible, facile à maintenir et à hacker.

---
## Screenshot

![FY59 nvim starter](assets/screen.jpg)

## 📂 Structure

```bash
❯ tree
.
├── assets
├── init.lua
├── lazy-lock.json
├── lua
│   ├── config
│   │   ├── lazy.lua
│   │   └── maps.lua
│   └── plugins
│       ├── bufferline.lua
│       ├── cmp.lua
│       ├── colorscheme.lua
│       ├── filebrowser.lua
│       ├── gitsign.lua
│       ├── lsp.lua
│       ├── mini-icons.lua
│       ├── mini_map.lua
│       ├── neowiki.lua
│       ├── nvim-autopair.lua
│       ├── nvim-tree.lua.old
│       ├── outline.lua
│       ├── render-markdown.lua
│       ├── starter.lua
│       ├── telescope.lua
│       ├── treesitter.lua
│       ├── ui.lua
│       ├── vim-fugitive.lua
│       └── witch-key.lua
└── readme.md

5 directories, 24 files

```

- init.lua : options de base, leader, undo persistant, puis require("config.maps") et require("config.lazy").
- lua/config/ : configuration générique (lazy, keymaps).
- lua/plugins/ : un fichier par “gros bloc” de plugins (LSP, UI, Git, notes, etc.).

🔧 Prérequis
- Neovim ≥ 0.9 (idéalement 0.10+).
- Git.

    Optionnel mais recommandé sur Arch :

        - tree-sitter-cli (via npm, AUR ou cargo) pour Treesitter. 
        - lua-language-server, pyright (via Mason ou pacman) pour LSP. 

## Installation
Sauvegarder une éventuelle config existante :

```bash
mv ~/.config/nvim ~/.config/nvim.backup-$(date +%s)
```

Cloner ce repo :

```bash
git clone https://github.com/<ton-user>/<ton-repo-nvim>.git ~/.config/nvim
```

Lancer Neovim :

```bash
nvim
lazy.nvim se clone automatiquement.
```

Les plugins se téléchargent au premier :Lazy sync.

Lancer les checks de santé :

```
:checkhealth
:checkhealth nvim-treesitter
```

## Fonctionnalités

1. Base
Options Neovim de base (numeros relatifs, indent propre, clipboard système, undo persistant). [web:64][web:272]
Keymaps Lua propres (config/maps.lua).

2. Gestionnaire de plugins
folke/lazy.nvim

    avec import modulaire :

```lua
    lua
    require("lazy").setup({
      { import = "plugins" },
    }, ...)
```

3. UI / Navigation

- Thème: folke/tokyonight.nvim and catppuccin 
- Statusline : nvim-lualine/lualine.nvim.
- Tabs / buffers : akinsho/bufferline.nvim
- Mode buffers, diagnostics LSP dans chaque “onglet”, icône de fermeture par buffer. [web:254][web:256]
- Fuzzy finder : nvim-telescope/telescope.nvim:
    <leader>ff : find_files (inclut les fichiers cachés). 
    <leader>fg : live_grep (avec --hidden). 
- File browser : telescope-file-browser.nvim, mappé sur <leader>e. 

4. Syntaxe / Treesitter

- nvim-treesitter/nvim-treesitter
    ensure_installed : Lua, Python, Bash, Markdown, Vimscript, etc.
    Highlight + indent activé

5. LSP
    - mason.nvim + mason-lspconfig.nvim.
    - nvim-lspconfig avec configuration minimale.
    - lua_ls pour Lua, avec vim en global autorisé.

Mappings LSP globaux :

gd, gr, K, <leader>rn, <leader>ca, [d, ]d, etc. 

6. Completion
- hrsh7th/nvim-cmp

Sources : LSP, buffer, path (cmp-nvim-lsp, cmp-buffer, cmp-path).

Mappings :
    Ctrl-j / Ctrl-k : naviguer.
    Enter : confirmer (sélection par défaut). 

7. Édition / Confort
- windwp/nvim-autopairs (InsertEnter). 
- hedyhli/outline.nvim

Keymaps personnalisés :
- Indent visuel avec Tab / Shift-Tab.
- Navigation buffers via bufferline (<leader>bp, <leader>bn, <leader>1..9).

8. Git (optionnel)
- lewis6991/gitsigns.nvim pour les signes Git dans la marge.
- tpope/vim-fugitive

9. Notes / Wiki
- echaya/neowiki.nvim comme wiki moderne (successeur de Vimwiki). 

10. starter
- nvim-mini/mini.starter

Support Markdown + Treesitter, GTD, multiple wikis.

Mappings typiques (configurable) : <leader>ww pour ouvrir le wiki, navigation entre pages, tâches, etc.

## Keymaps principaux

- folke/which-key.nvim

- Leader = Space.

Mini.maps
- <leader>p : show mini.map

Fichiers / Navigation
- <leader>e : file browser Telescope.
- <leader>ff : Telescope find_files.
- <leader>fg : Telescope live_grep.

Buffers
- <leader>bp / <leader>bn : buffer précédent / suivant.
- <leader>1..9 : aller au buffer N (bufferline).

LSP
- gd : définition.
- gr : références.
- K : hover.
- <leader>rn : rename.
- <leader>ca : code action.
- [d / ]d : diagnostics précédent / suivant.

Édition
- <leader>w : save.
- <leader>q : quit.
- <leader>h : clear search.

En Visuel : Tab / Shift-Tab → indent/désindent la sélection.

