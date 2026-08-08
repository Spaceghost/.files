if exists('g:spaceghost_dotfiles_loaded')
  finish
endif
let g:spaceghost_dotfiles_loaded = 1

set nocompatible
filetype plugin indent on
syntax enable

set number
set relativenumber
set mouse=a
set hidden
set confirm
set autoread
set splitbelow
set splitright
set scrolloff=3
set sidescrolloff=5

set ignorecase
set smartcase
set incsearch
set hlsearch
set wildmenu
set completeopt=menuone,noselect

set expandtab
set tabstop=2
set softtabstop=2
set shiftwidth=2
set autoindent
set updatetime=250

if has('termguicolors')
  set termguicolors
endif

let mapleader = ' '
nnoremap <silent> <leader>w :write<CR>
nnoremap <silent> <leader>q :quit<CR>
