#!/bin/sh
# Run from anywhere: tests/shell-configs.sh
set -eu
repo=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

sh -n "$repo/.bash_spaceghost" "$repo/.ashrc" "$repo/.config/spaceghost/aliases.sh"
bash -n "$repo/.bash_spaceghost"
if command -v zsh >/dev/null 2>&1; then zsh -n "$repo/.zshrc"; fi
if command -v fish >/dev/null 2>&1; then fish -n "$repo/.config/fish/config.fish"; fi

test "$(bash --noprofile --norc -c '. "$1/.config/spaceghost/aliases.sh"; alias gs >/dev/null && echo yes' _ "$repo")" = yes
if command -v ash >/dev/null 2>&1; then
    test "$(ENV="$repo/.ashrc" ash -ic 'alias gs >/dev/null && echo yes')" = yes
fi
if command -v fish >/dev/null 2>&1; then
    # shellcheck disable=SC2016 # fish expands $argv, not the outer POSIX shell.
    test "$(SPACEGHOST_PLAIN_SHELL=1 fish --no-config -ic 'source $argv[1]/.config/fish/config.fish; functions -q ll; and echo yes' -- "$repo")" = yes
fi

if command -v nu >/dev/null 2>&1; then
    test "$(nu --config "$repo/.config/nushell/config.nu" -c 'print (which e | length)')" = 1
    test "$(nu --config "$repo/.config/nushell/config.nu" -c 'print (which ll | length)')" = 1
fi

if command -v starship >/dev/null 2>&1; then
    TERM=xterm-256color STARSHIP_CONFIG="$repo/.config/starship.toml" \
        starship prompt --path "$repo" --status 0 >/dev/null
fi
if command -v fzf >/dev/null 2>&1; then
    . "$repo/.config/spaceghost/theme.sh"
    test "$(printf 'spaceghost\nother\n' | fzf --filter spaceghost)" = spaceghost
fi

tmp=$(mktemp -d)
trap 'rm -r "$tmp"' EXIT HUP INT TERM
cat > "$tmp/codex" <<'EOF'
#!/bin/sh
printf '%s\n' "$@"
EOF
chmod +x "$tmp/codex"
PATH="$tmp:$PATH" "$repo/.bin/ocodex" --help 'two words' > "$tmp/actual"
printf '%s\n' --search --dangerously-bypass-approvals-and-sandbox -s danger-full-access --help 'two words' > "$tmp/expected"
cmp "$tmp/actual" "$tmp/expected"

printf 'PASS shell configs and portable ocodex command\n'
