"""Gruvbox boot console: kernel palette parameters, GRUB edits and console banners."""
import configparser
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
BOOT = REPO / 'alpine/system/boot'
sys.path.insert(0, str(BOOT))
import boot_console as bc  # noqa: E402

loader = importlib.machinery.SourceFileLoader('install_boot_console',
                                              str(REPO / 'alpine/bin/install-boot-console'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)

GRUB_DEFAULT = '''GRUB_TIMEOUT=1
GRUB_DISABLE_SUBMENU=y
GRUB_DISABLE_RECOVERY=true
GRUB_CMDLINE_LINUX_DEFAULT="modules=sd-mod,usb-storage,ext4 cryptroot=UUID=06b2943c cryptdm=root quiet rootfstype=ext4"
'''

GRUB_CFG = '''### BEGIN /etc/grub.d/00_header ###
if [ "${next_entry}" ] ; then
   set default="${next_entry}"
else
   set default="0"
fi
set timeout=1
### END /etc/grub.d/00_header ###

### BEGIN /etc/grub.d/10_linux ###
menuentry 'Alpine Linux edge, with Linux lts' --class gnu-linux --class gnu --class os $menuentry_id_option 'gnulinux-lts-advanced-4b064483' {
\tload_video
\tinsmod gzio
\tinsmod part_gpt
\tinsmod fat
\tset root='hd0,gpt1'
\tif [ x$feature_platform_search_hint = xy ]; then
\t  search --no-floppy --fs-uuid --set=root --hint-efi=hd0,gpt1  DBEB-0144
\telse
\t  search --no-floppy --fs-uuid --set=root DBEB-0144
\tfi
\techo\t'Loading Linux lts ...'
\tlinux\t/vmlinuz-lts root=/dev/mapper/vg0-lv_root ro  modules=sd-mod,usb-storage,ext4 cryptroot=UUID=06b2943c cryptdm=root quiet rootfstype=ext4%s
\techo\t'Loading initial ramdisk ...'
\tinitrd\t%s
}

### END /etc/grub.d/10_linux ###

### BEGIN /etc/grub.d/30_uefi-firmware ###
menuentry 'UEFI Firmware Settings' $menuentry_id_option 'uefi-firmware' {
\tfwsetup
}
### END /etc/grub.d/30_uefi-firmware ###

### BEGIN /etc/grub.d/40_custom ###
# This file provides an easy way to add custom menu entries.  Simply type the
# menu entries you want to add after this comment.  Be careful not to change
# the 'exec tail' line above.
%s### END /etc/grub.d/40_custom ###
'''

CUSTOM_STOCK = '''#!/bin/sh
exec tail -n +3 $0
# This file provides an easy way to add custom menu entries.  Simply type the
# menu entries you want to add after this comment.  Be careful not to change
# the 'exec tail' line above.
'''


def cfg(extra='', initrd='/initramfs-lts', custom=''):
    return GRUB_CFG % (extra, initrd, custom)


class Palette(unittest.TestCase):
    def setUp(self):
        self.palette = bc.load_palette((BOOT / 'console-palette.json').read_text())
        self.parameters = bc.kernel_parameters(self.palette)

    def test_parameters_are_the_gruvbox_channels_in_ansi_order(self):
        self.assertEqual(self.parameters, [
            'vt.default_red=40,204,152,215,69,177,104,168,146,251,184,250,131,211,142,235',
            'vt.default_grn=40,36,151,153,133,98,157,153,131,73,187,189,165,134,192,219',
            'vt.default_blu=40,29,26,33,136,134,106,132,116,52,38,47,152,155,124,178',
            'vt.color=0x0F',
            'fbcon=font:TER16x32',
        ])

    def test_palette_matches_the_foot_terminal_colours(self):
        foot = configparser.ConfigParser(interpolation=None)
        foot.read(REPO / 'alpine/desktop/.config/foot/foot.ini')
        colours = [foot['colors-dark']['regular%d' % i] for i in range(8)]
        colours += [foot['colors-dark']['bright%d' % i] for i in range(8)]
        self.assertEqual([value.lstrip('#') for value in self.palette['colors']], colours)

    def test_invalid_palettes_are_rejected(self):
        for broken in ({'colors': ['#282828'] * 15, 'font': 'TER16x32',
                        'default_foreground': 15, 'default_background': 0},
                       {'colors': ['282828'] + ['#282828'] * 15, 'font': 'TER16x32',
                        'default_foreground': 15, 'default_background': 0},
                       {'colors': ['#282828'] * 16, 'font': '../x',
                        'default_foreground': 15, 'default_background': 0},
                       {'colors': ['#282828'] * 16, 'font': 'TER16x32',
                        'default_foreground': 16, 'default_background': 0}):
            with self.assertRaises(ValueError):
                bc.load_palette(json.dumps(broken))


class GrubDefault(unittest.TestCase):
    def setUp(self):
        self.parameters = bc.kernel_parameters(bc.load_palette((BOOT / 'console-palette.json').read_text()))

    def test_managed_tokens_are_appended_and_everything_else_survives(self):
        rewritten = bc.rewrite_grub_default(GRUB_DEFAULT, self.parameters)
        self.assertTrue(rewritten.startswith('GRUB_TIMEOUT=1\nGRUB_DISABLE_SUBMENU=y\nGRUB_DISABLE_RECOVERY=true\n'))
        tokens = bc.cmdline_tokens(rewritten)
        self.assertEqual(tokens[:6], ['modules=sd-mod,usb-storage,ext4', 'cryptroot=UUID=06b2943c',
                                      'cryptdm=root', 'quiet', 'rootfstype=ext4', self.parameters[0]])
        self.assertEqual(tokens[5:], self.parameters)

    def test_rewrite_is_idempotent_and_replaces_stale_managed_values(self):
        once = bc.rewrite_grub_default(GRUB_DEFAULT, self.parameters)
        self.assertEqual(bc.rewrite_grub_default(once, self.parameters), once)
        stale = GRUB_DEFAULT.replace('quiet', 'quiet vt.default_red=1,2,3 fbcon=font:VGA8x16')
        self.assertEqual(bc.rewrite_grub_default(stale, self.parameters), once)

    def test_missing_or_quoted_lines_are_refused(self):
        with self.assertRaises(ValueError):
            bc.rewrite_grub_default('GRUB_TIMEOUT=1\n', self.parameters)
        with self.assertRaises(ValueError):
            bc.rewrite_grub_default('GRUB_CMDLINE_LINUX_DEFAULT="a $b"\n', self.parameters)


class Issue(unittest.TestCase):
    def test_template_renders_to_ascii_with_sixteen_colour_escapes(self):
        rendered = bc.render_issue((BOOT / 'issue.template').read_text())
        self.assertNotIn(b'{', rendered)
        self.assertIn(b'\033[1;93mGHOST PLANET\033[0m', rendered)
        self.assertIn(b'\\n', rendered)  # getty hostname escape survives
        self.assertTrue(rendered.endswith(b'\033[0m\n\n'))
        rendered.decode('ascii')

    def test_percent_and_unknown_escapes_are_rejected(self):
        with self.assertRaises(ValueError):
            bc.render_issue('100% {reset}')
        with self.assertRaises(ValueError):
            bc.render_issue('\\x {reset}')
        with self.assertRaises(ValueError):
            bc.render_issue('{purple}')


class GhostEntry(unittest.TestCase):
    def test_entry_is_the_stock_entry_with_another_title_id_and_initramfs(self):
        entry = bc.ghost_menuentry(cfg())
        stock = bc.stock_entry(cfg())[1]
        self.assertIn("menuentry 'Alpine Linux edge, with Linux lts (Ghost Planet initramfs)'", entry)
        self.assertIn("'gnulinux-lts-advanced-4b064483-ghost'", entry)
        self.assertIn('\tinitrd\t/initramfs-lts-ghost\n', entry)
        kernel, tokens, _ = bc.entry_lines(entry)
        self.assertEqual((kernel, tokens), bc.entry_lines(stock)[:2])
        self.assertEqual(len(entry.splitlines()), len(stock.splitlines()))

    def test_custom_fragment_is_replaced_in_place(self):
        entry = bc.ghost_menuentry(cfg())
        once = bc.render_custom_fragment(CUSTOM_STOCK, entry)
        self.assertTrue(once.startswith(CUSTOM_STOCK))
        self.assertEqual(bc.render_custom_fragment(once, entry), once)
        changed = bc.render_custom_fragment(once, entry.replace('ghost\n', 'ghost-2\n'))
        self.assertEqual(changed.count(bc.CUSTOM_BEGIN), 1)
        self.assertIn('/initramfs-lts-ghost-2', changed)
        self.assertEqual(bc.remove_custom_fragment(once), CUSTOM_STOCK)
        with self.assertRaises(ValueError):
            bc.render_custom_fragment('menuentry x {}\n', entry)


class Validation(unittest.TestCase):
    def setUp(self):
        self.parameters = bc.kernel_parameters(bc.load_palette((BOOT / 'console-palette.json').read_text()))
        self.extra = ' ' + ' '.join(self.parameters)

    def test_accepts_the_same_boot_plus_managed_tokens(self):
        bc.validate_generated_cfg(cfg(), cfg(self.extra), self.parameters)
        stale = cfg(' vt.default_red=1,2,3')
        bc.validate_generated_cfg(stale, cfg(self.extra), self.parameters)

    def test_rejects_changed_root_initramfs_or_default(self):
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(self.extra).replace('cryptdm=root', 'cryptdm=other'), self.parameters)
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(self.extra, initrd='/initramfs-lts-ghost'), self.parameters)
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(self.extra).replace('set default="0"', 'set default="2"'), self.parameters)
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(), self.parameters)

    def test_ghost_entry_must_exist_once_and_mirror_the_stock_entry(self):
        entry = bc.ghost_menuentry(cfg(self.extra))
        with_ghost = cfg(self.extra, custom=entry + '\n')
        bc.validate_generated_cfg(cfg(), with_ghost, self.parameters, ghost_initrd='/initramfs-lts-ghost')
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), with_ghost, self.parameters)
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(self.extra), self.parameters, ghost_initrd='/initramfs-lts-ghost')
        with self.assertRaises(ValueError):
            bc.validate_generated_cfg(cfg(), cfg(self.extra, custom=entry.replace('quiet', 'loud') + '\n'),
                                      self.parameters, ghost_initrd='/initramfs-lts-ghost')


class InitPatch(unittest.TestCase):
    def test_banner_is_inserted_once_before_the_root_mount(self):
        stock = 'if [ -n "$KOPT_root" ]; then\n\tebegin "Mounting root"\n\tnlplug-findfs\nfi\n'
        patched = bc.patch_init(stock)
        self.assertEqual(patched.count('GHOST PLANET'), 1)
        self.assertTrue(patched.endswith('\tebegin "Mounting root"\n\tnlplug-findfs\nfi\n'))
        self.assertTrue(patched.startswith('if [ -n "$KOPT_root" ]; then\n\t# Oldbook'))
        with self.assertRaises(ValueError):
            bc.patch_init(patched)
        with self.assertRaises(ValueError):
            bc.patch_init('nothing here\n')
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as handle:
            handle.write('#!/bin/sh\nKOPT_root=x\nKOPT_cryptroot=y\nebegin() { :; }\nnlplug-findfs() { :; }\n' + patched)
        subprocess.run(['sh', '-n', handle.name], check=True)
        output = subprocess.run(['sh', handle.name], check=True, capture_output=True).stdout
        self.assertIn(b'\033[1;93mGHOST PLANET\033[0m', output)


class InstallerWrites(unittest.TestCase):
    def test_write_backs_up_restores_and_records_created_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'etc/default/grub'
            target.parent.mkdir(parents=True)
            target.write_text('before\n')
            job = installer.Installer(root / 'backup')
            self.assertTrue(job.write(target, b'after\n', 0o644))
            # The backup mirrors the absolute layout of the written path.
            self.assertEqual((root / 'backup' / target.relative_to('/')).read_text(), 'before\n')
            self.assertFalse(job.write(target, b'after\n', 0o644))
            self.assertEqual(target.read_text(), 'after\n')
            created = root / 'etc/issue'
            self.assertTrue(job.write(created, b'banner\n', 0o644))
            self.assertEqual(job.manifest['created'], [str(created)])
            job.restore_all()
            self.assertEqual(target.read_text(), 'before\n')
            self.assertFalse(created.exists())


class Listings(unittest.TestCase):
    def test_listing_names_are_normalised_and_compared(self):
        stock = '.\n./init\n./usr/lib/modules/6.18.49-0-lts/kernel/a.ko\n./etc/fstab\n'
        ghost = 'init\nusr/lib/modules/6.18.49-0-lts/kernel/a.ko\nusr/lib/firmware/new.bin\n'
        self.assertEqual(bc.parse_listing(stock), {'init', 'usr/lib/modules/6.18.49-0-lts/kernel/a.ko', 'etc/fstab'})
        self.assertEqual(bc.compare_listings(stock, ghost),
                         {'missing': ['etc/fstab'], 'extra': ['usr/lib/firmware/new.bin']})


if __name__ == '__main__':
    unittest.main()
