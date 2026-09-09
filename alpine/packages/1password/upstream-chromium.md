Paste into https://issues.chromium.org/issues/new
Component: Internals > Ozone > Wayland  (secondary: Internals > GPU > Buffers)
Type: Bug.  OS: Linux.  Title below.

---

TITLE

Ozone/Wayland sends DRM_FORMAT_MOD_LINEAR for implicitly allocated GBM buffers, corrupting windows on drivers with no modifier support

---

WHAT HAPPENED

On a GPU whose driver advertises no DRM format modifiers, Chromium allocates its
window buffer with gbm_bo_create(), asks gbm_bo_get_modifier() what layout it
got, and receives DRM_FORMAT_MOD_LINEAR (0). It then sends that 0 as an explicit
modifier in zwp_linux_buffer_params_v1.add(). The compositor imports the buffer
as strictly linear, which it is not, and the window renders with red and blue
transposed, interlaced text, horizontally sheared bands, and patches of
unrelated video memory from other windows.

The returned 0 is a fallback value in Mesa's GBM, not a description of the
layout. The same GBM device refuses gbm_bo_create_with_modifiers() for LINEAR,
because it has no modifier support at all. Chromium cannot distinguish "this
buffer is linear" from "I do not track modifiers", and currently assumes the
former.

STEPS TO REPRODUCE

1. Use an AMD GCN 1.0 card bound to the legacy `radeon` kernel driver rather
   than `amdgpu` (radeon.si_support=1, amdgpu.si_support=0). Any driver that
   advertises no format modifiers should do.
2. Run a wlroots-based compositor with an output at scale 2.
3. Launch a Chromium or Electron app with default flags and let it map a window
   wider than roughly 1000 logical pixels.

EXPECTED

The window renders correctly, as it does with --disable-gpu-compositing, and as
Firefox does on the same GPU, compositor and session.

ACTUAL

The window is corrupted as described. Adding --disable-gpu-compositing, which
switches Chromium to wl_shm buffers, renders correctly and bit-identically
across runs.

EVIDENCE

Probe against the render node:

  has EGL_EXT_image_dma_buf_import_modifiers: True
  eglQueryDmaBufModifiersEXT present:         True
  modifiers advertised for ARGB8888:          0

  gbm_bo_create(1414, 789, AR24, GBM_BO_USE_RENDERING)
      -> stride=5888  modifier=0x0000000000000000
  gbm_bo_create_with_modifiers(..., [DRM_FORMAT_MOD_LINEAR], 1)
      -> FAILED, driver advertises no modifiers

WAYLAND_DEBUG=1 for the corrupted toplevel, 1414x789 logical at scale 2:

  -> zwp_linux_dmabuf_v1#5.create_params(new id zwp_linux_buffer_params_v1#40)
  -> zwp_linux_buffer_params_v1#40.add(fd 137, 0, 0, 5888, 0, 0)
  -> zwp_linux_buffer_params_v1#40.create_immed(new id wl_buffer#41, 1414, 789, 875708993, 0)

modifier_hi and modifier_lo are both 0, so LINEAR is asserted explicitly.
Format 875708993 is AR24 / DRM_FORMAT_ARGB8888. Stride 5888 is the width padded
from 1414 to 1472 pixels, so the buffer is not tightly packed linear either.

Firefox on the same device also uses dmabuf and also sends modifier 0, but its
buffers come back tightly packed, for example 2560x1620 XR24 with stride 10240,
exactly width times four. A buffer whose declared linear stride matches its
real layout survives a linear import; a padded, driver-tiled one does not.

Measured over three cold starts each against a reference frame, the default
launch differed every time, worst case 3.22 percent of pixels; with
--disable-gpu-compositing the frame was bit-identical every time. A Foot
terminal and Firefox in the same compositor were correct throughout, so neither
the compositor nor the driver is implicated.

SUGGESTED FIX

In ui/ozone/platform/wayland and ui/gfx/linux/gbm_wrapper.cc, do not pair
gbm_bo_create() with a trusted gbm_bo_get_modifier(). Either allocate with
gbm_bo_create_with_modifiers(), or send DRM_FORMAT_MOD_INVALID for implicitly
allocated buffers so the compositor negotiates the layout out of band.

Mesa maintainers described this pairing as API misuse when closing
https://gitlab.freedesktop.org/mesa/mesa/-/merge_requests/26296 in 2023:
"chrome always uses gbm_bo_get_modifier to get the modifier, but does not always
use gbm_bo_create_with_modifiers to allocate the bo." The author also proposed
making GBM return DRM_FORMAT_MOD_INVALID consistently, which was never done, so
the Chromium side is currently the only place this can be fixed.

ENVIRONMENT

  GPU             AMD Radeon R9 M370X, Venus XT / Cape Verde, PCI 1002:6821
  Kernel driver   radeon (radeon.si_support=1, amdgpu.si_support=0)
  Mesa            26.1.6
  libdrm          2.4.134
  Kernel          6.18.49
  Compositor      SwayFX 0.6 on wlroots 0.20.2, scenefx 0.5
  Display         2880x1800, wl_output scale 2
  Client          1Password 8.12.12 (Electron), Flathub,
                  org.freedesktop.Platform 25.08
  Host            MacBookPro11,5, Alpine Linux edge
