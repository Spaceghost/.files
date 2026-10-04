# Behold, $SHELL mode: an interactive terminal lands in Neovim's :terminal.
# zsh stays the login shell; Neovim is the multiplexer (~/.config/nvim/init.lua).
# Skipped inside Neovim, inside tmux (tmux is already the multiplexer there), or
# with SPACEGHOST_PLAIN_SHELL=1 for one plain shell.
if [[ -o interactive && -t 0 && -t 1 && -z $NVIM && -z $TMUX && -z $SPACEGHOST_PLAIN_SHELL ]] \
    && (( $+commands[nvim] )); then
    exec nvim
fi
