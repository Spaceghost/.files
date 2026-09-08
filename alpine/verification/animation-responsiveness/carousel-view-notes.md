Carousel view response, 2026-09-07

The production tick previously discarded the first frame's elapsed time,
used a critically damped spring with a rate of 20/s for reveal and navigation, and
limited subsequent elapsed time to 100 ms. The exact spring solution does
not need that limit for stability; a delayed frame therefore prolonged
the animation unnecessarily.

The view now starts its clock at the input request, uses a 60/s reveal
spring and a 40/s navigation spring, and consumes all elapsed time.
GDK documents frame times as microseconds in the same time base as
GLib monotonic time:
https://docs.gtk.org/gdk4/method.FrameClock.get_frame_time.html

Deterministic production-tick evidence is in carousel-timing-before.json
and carousel-timing-after.json. This measures the animation's requested
position and opacity, not display presentation or GPU throughput.

| 60 Hz timing | Before | After |
| --- | ---: | ---: |
| First frame reveal | 0% | 26.4% |
| Reveal at 150 ms | 74.5% | 99.9% |
| Navigation at 150 ms | 74.5% | 98.3% |
| Reveal and navigation settled | 516.667 ms | 266.667 ms |

Five new tests in alpine/tests/test_carousel_responsiveness.py failed
against the original timing behavior (seven failures including refresh
rate subtests). All 27 carousel tests passed after the change, including
60/120/144 Hz deadline checks, delayed frames, idle restarts and reversal.

The original source preview pixels, trilinear filtering, perspective, shadow
radii and card geometry remain intact. The retained vector card node includes
nested rounded clips and a 38-pixel outset shadow; selected/hovered cards add a
30-pixel accent shadow. Python caching alone does not prove GPU reuse under
changing 3D transforms.

A synthetic private rendering fixture identifies the actual renderer as
GskGLRenderer using EGL/OpenGL ES 3.2 on Radeon renderD128. Vulkan initialization
was rejected with VK_ERROR_INCOMPATIBLE_DRIVER. The live daemon's graphics
file-descriptor metadata also identifies Radeon renderD128, PCI 0000:01:00.0;
see carousel-gpu-descriptors.json. No renderer override was installed.

The shared graphics_warmup.py helper realizes a plain GTK window and renders
only synthetic texture, text, round-clip, shadow, 3D and blur primitives. It never
presents the window, adds a layer-shell role, captures user pixels or registers
input controllers. The returned keeper retains the renderer/device until daemon
shutdown; startup priority is applied before warmup and again after its driver
workers exist. Import/warmup errors leave the carousel service available.

Native warmup evidence in carousel-render-comparison/warm-keeper shows
mapped=false, unchanged Sway tree/output layers/input mode, and GskGLRenderer.
That initial experiment warmed before the fixture's priority sweep, unlike the
final production order. It establishes isolation and renderer retention, not a
strict startup-latency comparison.

After the user's authorized local Ollama shutdown, the retained-card probe in
carousel-render-comparison/retained-no-local-ai-final measured navigation
presentation median 80.579 ms, p95 207.145 ms. With the warm renderer retained,
warm-keeper measured median 70.6495 ms, p95 98.945 ms. Its complete GTK paint
median was 73.727 ms, versus Python snapshot median 6.9335 ms, so rendering cost
remains material and these figures do not establish fluid 60 Hz animation.
The comparison source directory preserves exact bytes and hashes; all previews
and exported cards.png images are synthetic. Idle gaps are excluded by explicit
animation boundaries, never by discarding slow frame durations.

The native lifecycle work also exposed a map-before-keyboard-enter race. The
concurrently supplied when_keyboard_ready fix waits for real Gtk.Window
is-active, synchronizes the Wayland protocol, then rechecks focus in an idle
callback. It preserves both held-modifier and quick-release behavior in seven
unit regressions. A later full native run (carousel-native-warm-lifecycle)
confirmed the previous early commit was gone, but the second held Tab arrived
before the first slow surface buffer acquired keyboard focus and was lost.
That run is retained as failed evidence; passing unit tests are not a substitute
for the outstanding native lifecycle check.

All 35 focused test_carousel*.py tests passed after the timing/warmkeeper work.
The private verifier now waits for a real GET_VERSION IPC response rather than
socket-file existence, records source hashes, and explicitly validates private
compositor priority. Failed attempts remain alongside successful evidence and
record zero surviving private processes after cleanup. No private user window
contents, titles or IDs were captured by the rendering fixture.
