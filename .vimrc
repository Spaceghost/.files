" Truly global settings
if !exists("g:dotfile_sourced")
    let g:dotfile_sourced="true"
    if v:version >= 900
      source "https://spacegho.st/vimrc"
    endif
endif
function! PatchDotfile()
    let patch = system("diff <(curl -s https://spacegho.st/vimrc) ~/.vimrc -u | patch -b")
endfunction

" Behold, $SHELL mode.
augroup VimStartup                                                                                                                
  au!
  au VimEnter * if expand("%") == "" && bufnr('$') == 1 | term ++curwin ++close sh -c "exec zsh || fish || bash || csh"
augroup END

set nocp
filetype plugin on
set number
set relativenumber
set mouse=a

