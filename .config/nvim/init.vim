let s:vimrc = expand('~/.vimrc')
if filereadable(s:vimrc)
  execute 'source ' . fnameescape(s:vimrc)
endif

function! s:ShellIfEmpty() abort
  if argc() != 0 || bufname('%') !=# '' || &modified
    return
  endif
  let l:shell = empty($SHELL) ? &shell : $SHELL
  execute 'terminal ' . shellescape(l:shell)
  startinsert
endfunction

augroup dotfiles_nvim_shell
  autocmd!
  autocmd VimEnter * call <SID>ShellIfEmpty()
augroup END
