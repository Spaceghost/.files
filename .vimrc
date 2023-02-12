" Truly global settings
if !exists("g:dotfile_sourced")
    let g:dotfile_sourced="true"
    source "https://raw.githubusercontent.com/Spaceghost/.files/base/.vimrc"
endif

" Behold, $SHELL mode.
augroup VimStartup                                                                                                                
  au!
  au VimEnter * if expand("%") == "" && bufnr('$') == 1 | term ++curwin ++close sh -c "exec zsh || fish || bash"
augroup END

set nocp
filetype plugin on
set number
set relativenumber
set mouse=a