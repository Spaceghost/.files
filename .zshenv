# zshenv - Always sourced.

(( $+commands[brew] )) && export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$(brew --prefix openssl@3)"

# Edit inside the running Neovim (see ~/.config/nvim/init.lua, ~/.bin/nvim-remote).
[[ -d $HOME/.local/bin && ":$PATH:" != *":$HOME/.local/bin:"* ]] && export PATH="$HOME/.local/bin:$PATH"
[[ -d $HOME/.local/nvim/bin && ":$PATH:" != *":$HOME/.local/nvim/bin:"* ]] && export PATH="$HOME/.local/nvim/bin:$PATH"
export PATH="$HOME/.bin:$PATH"
if [[ -z ${TMPDIR:-} ]]; then
    for spaceghost_tmp in /srv/ai/tmp "$HOME/.cache/spaceghost/tmp"; do
        if [[ -d $spaceghost_tmp && -w $spaceghost_tmp ]]; then
            export TMPDIR="$spaceghost_tmp"
            break
        fi
    done
    unset spaceghost_tmp
fi
if [[ ${TMPDIR:-} == /srv/ai/tmp ]]; then
    export AI_WORKSPACE_ROOT=/srv/ai TMP="$TMPDIR" TEMP="$TMPDIR"
fi
export EDITOR="$HOME/.bin/nvim-remote"
export VISUAL="$EDITOR"
export ENV="$HOME/.ashrc"
[[ -r $HOME/.files/.config/spaceghost/theme.sh ]] && source "$HOME/.files/.config/spaceghost/theme.sh"
