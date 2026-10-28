(use-modules (gnu home)
             (gnu home services)
             (gnu home services sound)
             (gnu packages)
             (guix gexp)
             (ice-9 ftw)
             (ice-9 match)
             (srfi srfi-1))

(define %checkout
  (canonicalize-path (string-append (dirname (current-filename)) "/..")))

(define %desktop
  (string-append %checkout "/alpine/desktop"))

(define (store-file name path)
  (local-file path name #:recursive? (file-is-directory? path)))

(define (visible-entries directory)
  (filter (lambda (name)
            (not (member name '("." ".."))))
          (scandir directory)))

(define (configuration-entry name)
  (cons name
        (store-file (string-append "oldbook-config-" name)
                    (string-append %desktop "/.config/" name))))

;; Packages which form the portable part of the current Alpine world.  A few
;; project-specific packages do not exist in Guix yet; README.md tracks those
;; without silently substituting a different desktop behavior.
(define %desktop-package-specifications
  '("adwaita-icon-theme"
    "bash"
    "brightnessctl"
    "btop"
    "cava"
    "cliphist"
    "conky"
    "curl"
    "dbus"
    "eza"
    "fastfetch"
    "font-dejavu"
    "font-google-noto"
    "font-jetbrains-mono"
    "foot"
    "fossil"
    "fuzzel"
    "git"
    "glib"
    "gnome-keyring"
    "grim"
    "imv"
    "iproute2"
    "iw"
    "jq"
    "libnotify"
    "mpv"
    "neovim"
    "nftables"
    "pavucontrol"
    "playerctl"
    "python"
    "python-pygobject"
    "python-numpy"
    "qt6ct"
    "ripgrep"
    "satty"
    "shellcheck"
    "slurp"
    "starship"
    "sway"
    "swaybg"
    "swayidle"
    "swaylock"
    "swaynotificationcenter"
    "thunar"
    "tmux"
    "waybar"
    "wf-recorder"
    "wireplumber"
    "wl-clipboard"
    "wlsunset"
    "wmenu"
    "wtype"
    "xdg-desktop-portal-gtk"
    "xdg-desktop-portal-wlr"
    "xorg-server-xwayland"
    "yt-dlp"
    "zoxide"
    "zsh"))

(define (resolve-package specification)
  ;; A pinned channel may temporarily lack a leaf application.  Preserve an
  ;; evaluable recovery generation and print the exact omission; never replace
  ;; it with an unrelated package.
  (catch #t
    (lambda () (specification->package specification))
    (lambda arguments
      (format (current-error-port)
              "oldbook: package unavailable in pinned channels: ~a~%"
              specification)
      #f)))

(home-environment
 (packages (filter-map resolve-package %desktop-package-specifications))
 (services
  (list
   (service home-pipewire-service-type
            (home-pipewire-configuration
             (enable-pulseaudio? #t)))
   (service home-xdg-configuration-files-service-type
            (map configuration-entry
                 (visible-entries (string-append %desktop "/.config"))))
   (service home-files-service-type
            `(;; Keep the executable Oldbook implementation and its data as one
              ;; immutable tree.  Theme switching still writes generated files
              ;; through the checkout until it gains an explicit state root.
              (".local" . ,(store-file "oldbook-local"
                                       (string-append %desktop "/.local")))
              (".tmux.conf" . ,(store-file "oldbook-tmux.conf"
                                           (string-append %desktop "/.tmux.conf")))
              (".zshrc" . ,(store-file "oldbook-zshrc"
                                      (string-append %desktop "/.zshrc")))))
   (simple-service
    'oldbook-session-environment
    home-environment-variables-service-type
    `(("BROWSER" . "firefox")
      ("EDITOR" . "nvim")
      ("GTK_THEME" . "Oldbook")
      ("OLDBOOK_CHECKOUT" . ,%checkout)
      ("QT_QPA_PLATFORM" . "wayland;xcb")
      ("QT_QPA_PLATFORMTHEME" . "qt6ct")
      ("SPACEGHOST_SCREEN_CORNER_RADIUS" . "20")
      ("TERMINAL" . "ghostty")
      ("XCURSOR_SIZE" . "24")
      ("XCURSOR_THEME" . "Oldbook-Ghost")
      ("XDG_CURRENT_DESKTOP" . "sway")
      ("XDG_SESSION_TYPE" . "wayland"))))))
