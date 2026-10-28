(use-modules (gnu packages)
             (guix profiles))

;; This first foreign-distro profile is deliberately non-graphical.  The live
;; desktop continues to use the hash-pinned Alpine packages until equivalent
;; Guix recipes have been built on a remote builder and pass audit-current.
(packages->manifest
 (specifications->packages
  '("guile"
    "jq"
    "ripgrep")))
