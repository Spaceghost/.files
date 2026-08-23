set nocompatible
filetype plugin indent on
syntax enable

set number
set relativenumber
set mouse=a
set hidden
set autoread
set ignorecase
set smartcase
set incsearch
set hlsearch
set splitbelow
set splitright
set wildmenu
set wildmode=longest:full,full
set completeopt=menuone,noselect
set updatetime=300

if exists('+signcolumn')
  set signcolumn=yes
endif

if exists('+termguicolors')
  set termguicolors
endif

" Preserve the repo's original idea: an empty Vim is a useful shell wrapper.
if has('terminal') && !has('nvim')
  function! s:ShellIfEmpty() abort
    if argc() != 0 || bufname('%') !=# '' || &modified
      return
    endif
    let l:shell = empty($SHELL) ? &shell : $SHELL
    execute 'terminal ++curwin ++close ' . shellescape(l:shell)
  endfunction

  augroup dotfiles_shell
    autocmd!
    autocmd VimEnter * call <SID>ShellIfEmpty()
  augroup END
endif
