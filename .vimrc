set nocp
filetype plugin on

set relativenumber
" Augroup VimStartup:
augroup VimStartup
  au!
  au VimEnter * if expand("%") == "" | term ++curwin
augroup END
set mouse=a
hi Terminal ctermbg=black ctermfg=green guibg=black guifg=white