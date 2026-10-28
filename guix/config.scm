(use-modules (gnu)
             (gnu packages)
             (gnu services)
             (gnu services base)
             (gnu services desktop)
             (gnu services networking)
             (gnu services sound)
             (gnu system mapped-devices)
             (nongnu packages linux)
             (nongnu system linux-initrd)
             (guix gexp)
             (srfi srfi-1))

(define %checkout
  (canonicalize-path (string-append (dirname (current-filename)) "/..")))

(define %luks-devices
  (list (mapped-device
         (source (uuid "06b2943c-7831-4617-9e6f-691a388c795e"))
         (target "root")
         (type luks-device-mapping))))

(define %oldbook-system-packages
  (specifications->packages
   '("cryptsetup"
     "dosfstools"
     "foot"
     "fossil"
     "git"
     "lvm2"
     "neovim"
     "nftables"
     "opendoas"
     "openssh"
     "python"
     "sway")))

(define (package-bin specification executable)
  (file-append (specification->package specification)
               (string-append "/bin/" executable)))

(define %oldbook-fhs-links
  ;; The existing desktop is intentionally portable POSIX/Python code but some
  ;; launch and process-identity paths are absolute.  Keep those identities
  ;; stable while packages themselves remain in the Guix store.
  `(("/usr/bin/env" ,(package-bin "coreutils" "env"))
    ("/usr/bin/python3" ,(package-bin "python" "python3"))
    ("/usr/bin/foot" ,(package-bin "foot" "foot"))
    ("/usr/bin/btop" ,(package-bin "btop" "btop"))
    ("/usr/bin/nvim" ,(package-bin "neovim" "nvim"))
    ("/usr/bin/sway" ,(package-bin "sway" "sway"))
    ("/usr/bin/doas" ,(package-bin "opendoas" "doas"))))

(define %oldbook-sway-session
  (program-file
   "oldbook-sway-session"
   #~(begin
       (setenv "HOME" "/home/jack")
       (setenv "PATH"
               "/home/jack/.local/bin:/home/jack/.guix-home/profile/bin:/run/current-system/profile/bin")
       (setenv "XDG_CURRENT_DESKTOP" "sway")
       (setenv "XDG_DATA_DIRS"
               "/home/jack/.guix-home/profile/share:/run/current-system/profile/share")
       (setenv "XDG_SESSION_TYPE" "wayland")
       (setenv "QT_QPA_PLATFORMTHEME" "qt6ct")
       (setenv "SPACEGHOST_SCREEN_CORNER_RADIUS" "20")
       (execl #$(file-append (specification->package "sway") "/bin/sway")
              "sway" "--config" "/home/jack/.config/sway/config"))))

(define %oldbook-desktop-services
  ;; PipeWire is owned by Guix Home, so remove the system-wide PulseAudio
  ;; service before extending the normal desktop service set.
  (cons*
   (service bluetooth-service-type
            (bluetooth-configuration (auto-enable? #t)))
   (service greetd-service-type
            (greetd-configuration
             (allow-empty-passwords? #f)
             (greeter-supplementary-groups
              '("video" "input" "audio" "seat"))
             (terminals
              (list
               (greetd-terminal-configuration
                (terminal-vt "1")
                (terminal-switch #t)
                (default-session-user "jack")
                (default-session-command
                 (greetd-user-session
                  (command %oldbook-sway-session)
                  (command-args '())))
                (initial-session-user "jack")
                (initial-session-command
                 (greetd-user-session
                  (command %oldbook-sway-session)
                  (command-args '()))))))))
   (simple-service 'oldbook-fhs-links
                   special-files-service-type
                   %oldbook-fhs-links)
   (simple-service
    'oldbook-doas-policy
    etc-service-type
    `(("doas.conf"
       ,(plain-file
         "doas.conf"
         "# Authenticate wheel members; narrow passwordless helpers are added only with their Shepherd ports.\npermit persist :wheel\n"))))
   (remove (lambda (service)
             (eq? (service-kind service) pulseaudio-service-type))
           %desktop-services)))

(operating-system
 (host-name "catbed")
 (timezone "America/Los_Angeles")
 (locale "en_US.utf8")

 ;; BCM43602 Wi-Fi, Radeon firmware and Intel microcode are required on this
 ;; MacBookPro11,5 and are not distributed by the main Guix channel.
 (kernel linux-lts)
 (initrd microcode-initrd)
 (firmware (list linux-firmware))
 (kernel-arguments
  (list "quiet"
        "fbcon=font:TER16x32"
        "vt.color=0x0F"
        "module_blacklist=b43,b43legacy,ssb,brcmsmac,bcma"))

 (bootloader
  (bootloader-configuration
   (bootloader grub-efi-bootloader)
   (targets '("/boot"))
   (keyboard-layout (keyboard-layout "us"))))

 (mapped-devices %luks-devices)
 (file-systems
  (cons*
   (file-system
    (mount-point "/")
    (device "/dev/mapper/vg0-lv_root")
    (type "ext4")
    (dependencies %luks-devices))
   (file-system
    (mount-point "/boot")
    (device (uuid "DBEB-0144" 'fat32))
    (type "vfat"))
   %base-file-systems))
 (swap-devices
  (list (swap-space (target "/dev/mapper/vg0-lv_swap")
                    (dependencies %luks-devices))))

 (users
  (cons
   (user-account
    (name "jack")
    (comment "jack")
    (group "users")
    (uid 1000)
    ;; The encrypted-root prompt is the physical login gate.  Set a local
    ;; password after installation for sudo/TTY use; no hash belongs here.
    (password "!")
    (supplementary-groups
     '("wheel" "audio" "video" "input" "netdev" "seat")))
   %base-user-accounts))

 (packages (append %oldbook-system-packages %base-packages))
 (services %oldbook-desktop-services)
 (name-service-switch %mdns-host-lookup-nss))
