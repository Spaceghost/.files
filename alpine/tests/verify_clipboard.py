#!/usr/bin/env python3
"""Exercise the shipped clipboard integration in a private Sway/XWayland session."""
import base64,json,os,runpy,signal,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'alpine/verification/clipboard'
HELPER=ROOT/'alpine/desktop/.local/bin/oldbook-clipboard'
results={}
processes=[]
temp=tempfile.TemporaryDirectory(prefix='clipboard-integration-')
b=Path(temp.name); run=b/'run'; run.mkdir(mode=0o700)
home=b/'home'; (home/'.local/bin').mkdir(parents=True); (home/'.config/tmux').mkdir(parents=True)
(home/'.local/bin/oldbook-clipboard').symlink_to(HELPER)
(home/'.config/tmux/oldbook.conf').symlink_to(ROOT/'alpine/desktop/.config/tmux/oldbook.conf')
env=dict(os.environ,HOME=str(home),XDG_RUNTIME_DIR=str(run),XDG_STATE_HOME=str(b/'state'),XDG_CACHE_HOME=str(b/'cache'),XDG_CONFIG_HOME=str(home/'.config'),WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_HEADLESS_OUTPUTS='1')
for k in ('SWAYSOCK','WAYLAND_DISPLAY','DISPLAY','TMUX','CLIPHIST_DB_PATH'): env.pop(k,None)
log=(OUT/'runtime.log').open('w')
def start(args,**kw):
    p=subprocess.Popen(args,env=env,stdout=log,stderr=log,**kw); processes.append(p); return p
def cmd(args,**kw):
    try: return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,**kw)
    except subprocess.CalledProcessError as e:
        print('COMMAND FAILED',args,repr(e.stderr),flush=True)
        raise
def wait(fn,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        val=fn()
        if val: return val
        time.sleep(.08)
    raise RuntimeError('Timed out: '+str(fn))
def ipc(s):
    r=cmd(['swaymsg','-r',s],check=True)
    return json.loads(r.stdout)
def paste(): return cmd(['wl-paste','-n']).stdout
def copy(data,mime='text/plain;charset=utf-8'):
    cmd(['wl-copy','--type',mime],input=data,check=True)
def listing(): return cmd([str(HELPER),'list'],check=True).stdout
config=b/'sway.conf'
config.write_text('xwayland force\noutput HEADLESS-1 mode 1000x700\nseat seat0 fallback true\n'+f'exec sh -c \'printf "%s" "$DISPLAY" > {b}/display\'\n')
try:
    sway=start(['/usr/bin/sway','-c',str(config)])
    wait(lambda:list(run.glob('sway-ipc*.sock')))
    env['SWAYSOCK']=str(next(run.glob('sway-ipc*.sock')))
    env['WAYLAND_DISPLAY']=next(p.name for p in run.glob('wayland-*') if p.is_socket())
    wait(lambda:(b/'display').exists() and (b/'display').read_text())
    env['DISPLAY']=(b/'display').read_text()
    # A real non-manager owner disappears on exit before the fix.
    owner=start(['wl-copy','--foreground','--type','text/plain'],stdin=subprocess.PIPE)
    owner.stdin.write(b'baseline clipboard');owner.stdin.close()
    wait(lambda:paste()==b'baseline clipboard')
    owner.terminate();owner.wait()
    wait(lambda:paste()==b'')
    results['before_owner_exit_loses_clipboard']=True
    service=start([str(HELPER),'daemon'])
    time.sleep(.8)
    assert service.poll() is None
    duplicate=cmd([str(HELPER),'daemon'])
    assert duplicate.returncode==0
    results['daemon_reload_single_instance']=True
    text='  shared café clipboard\nsecond line\n\n'.encode()
    copy(text)
    wait(lambda:b'shared' in listing())
    assert paste()==text
    results['wayland_text_and_history']=True
    # Persistence process takes ownership, releasing the original foreground owner.
    owner=start(['wl-copy','--foreground','--type','text/plain'],stdin=subprocess.PIPE)
    owner.stdin.write(b'persists after owner exits');owner.stdin.close()
    wait(lambda:paste()==b'persists after owner exits')
    time.sleep(.5)
    if owner.poll() is None: owner.terminate()
    owner.wait()
    assert paste()==b'persists after owner exits'
    results['after_owner_exit_preserves_clipboard']=True
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
    copy(png,'image/png')
    wait(lambda:b'binary' in listing())
    assert cmd(['wl-paste','-n','-t','image/png']).stdout==png
    # Restore the actual binary history entry using a deterministic picker.
    picker=home/'.local/bin/oldbook-fuzzel'
    picker.write_text('#!/usr/bin/python3\nimport sys\nrows=sys.stdin.buffer.readlines()\nsys.stdout.buffer.write(next(r for r in rows if b"binary" in r))\n')
    picker.chmod(0o755)
    env['PATH']=str(home/'.local/bin')+':'+os.environ['PATH']
    copy(b'new text')
    cmd([str(HELPER),'pick'],check=True)
    assert cmd(['wl-paste','-n','-t','image/png']).stdout==png
    results['image_history_restores_exact_png']=True
    # Neovim's real provider, with the shipped config, transfers both ways.
    copy(b'from desktop to neovim')
    nvimout=b/'nvim.txt'
    lua=b/'nvim.lua'
    lua.write_text(f'vim.fn.writefile({{vim.fn.getreg("+")}}, {str(nvimout)!r})\nvim.fn.setreg("+", "from neovim to desktop")\nvim.wait(250)\n')
    r=cmd(['nvim','--headless','-u',str(ROOT/'alpine/desktop/.config/nvim/init.lua'),'-l',str(lua)])
    assert r.returncode==0,r.stderr
    assert nvimout.read_text().strip()=='from desktop to neovim'
    assert paste()==b'from neovim to desktop'
    results['neovim_bidirectional']=True
    # Attached tmux: vi y and default Enter must use the pipe without relying on OSC52.
    conf=b/'tmux.conf'
    conf.write_text(f'source-file "{ROOT}/alpine/desktop/.config/tmux/oldbook.conf"\nset -s set-clipboard off\n')
    socket=str(b/'tmux.sock')
    t=lambda *args: cmd(['tmux','-S',socket,*args],check=True)
    t('-f',str(conf),'new-session','-d','-s','fixture','sh','-c',"printf 'tmux clipboard fixture\\n'; sleep 120")
    terminal=start(['foot','--config',str(ROOT/'alpine/desktop/.config/foot/foot.ini'),'--app-id','clipboard-tmux','tmux','-S',socket,'attach','-t','fixture'])
    wait(lambda:bool(t('list-clients').stdout))
    wait(lambda: cmd(['swaymsg','-r','[app_id="clipboard-tmux"] focus']).returncode==0)
    t('source-file',str(conf))
    time.sleep(.3)
    for key in ('y','Return'):
        copy(b'before tmux')
        t('copy-mode');t('send-keys','-X','history-top');t('send-keys','-X','start-of-line');t('send-keys','-X','begin-selection');t('send-keys','-X','end-of-line')
        client=t('list-clients','-F','#{client_name}').stdout.decode().strip()
        t('send-keys','-K','-c',client, 'Enter' if key=='Return' else key)
        
        try: wait(lambda:paste()==b'tmux clipboard fixture')
        except Exception:
            print('TMUX DEBUG',key,repr(paste()),t('capture-pane','-p').stdout,t('show-options','-s','copy-command').stdout,cmd(['tmux','-S',socket,'show-buffer']).stdout,t('show-window-options','-g','mode-keys').stdout,flush=True)
            raise
        if key=='y': t('send-keys','-X','cancel')
    results['tmux_vi_y_and_enter_copy']=True
    t('kill-server')
    # Real GTK clients on Wayland and XWayland. Never use the user's session.
    gtk=b/'gtk.py'
    gtk.write_text('''import gi,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
mode,trigger,result=sys.argv[1:]
w=Gtk.Window(title='Clipboard GTK fixture');w.set_default_size(350,150);w.add(Gtk.Label(label='Synthetic clipboard integration fixture'));w.show_all()
c=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def tick():
    if not Path(trigger).exists():return True
    if mode=='copy':c.set_text('from GTK '+Gdk.Display.get_default().get_name(),-1);Path(result).write_text('ready')
    else:Path(result).write_text(c.wait_for_text() or '')
    return False
w.connect('key-press-event',lambda *args:tick())
Gtk.main()
''')
    for backend in ('wayland','x11'):
        trigger=b/(backend+'-trigger'); result=b/(backend+'-result')
        p=subprocess.Popen(['python3',str(gtk),'copy',str(trigger),str(result)],env=dict(env,GDK_BACKEND=backend),stdout=log,stderr=log);processes.append(p)
        def gtk_focus():
            return cmd(['swaymsg','-r','[title="Clipboard GTK fixture"] focus']).returncode==0
        wait(gtk_focus);trigger.touch();cmd(['wtype','-s','300','-k','space','-s','100'],check=True);wait(result.exists)
        
        try: wait(lambda:paste().startswith(b'from GTK '))
        except Exception:
            print('GTK DEBUG',backend,repr(paste()),cmd(['wl-paste','--list-types']).stdout,flush=True)
            raise
        p.terminate();p.wait()
        # Paste from a separate native owner into this backend's client.
        copy(b'desktop to '+backend.encode())
        trigger.unlink();result.unlink()
        p=subprocess.Popen(['python3',str(gtk),'paste',str(trigger),str(result)],env=dict(env,GDK_BACKEND=backend),stdout=log,stderr=log);processes.append(p)
        wait(gtk_focus);trigger.touch();cmd(['wtype','-s','300','-k','space','-s','100'],check=True);wait(result.exists)
        assert result.read_bytes()==b'desktop to '+backend.encode(),result.read_bytes()
        p.terminate();p.wait()
        results[backend+'_gtk_bidirectional']=True
    # Create a real virtual pointer capability before sending pointer events.
    pointer_binary=runpy.run_path(str(ROOT/'alpine/tests/verify_waybar_music.py'))['build_pointer'](b)
    pointer=subprocess.Popen([str(pointer_binary)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
    processes.append(pointer)
    assert pointer.stdout.readline().strip()=='ready'
    # Foot mouse selection reaches both clipboards.
    terminal=start(['foot','--config',str(ROOT/'alpine/desktop/.config/foot/foot.ini'),'--app-id','clipboard-foot','sh','-c',"printf 'FOOTCLIPBOARD\\n'; sleep 120"])
    wait(lambda:cmd(['swaymsg','-r','[app_id="clipboard-foot"] focus']).returncode==0)
    ipc('[app_id="clipboard-foot"] fullscreen enable')
    time.sleep(.5)
    copy(b'before foot selection')
    ipc('seat seat0 cursor set 40 10')
    for _ in range(2):
        ipc('seat seat0 cursor press button1');ipc('seat seat0 cursor release button1');time.sleep(.05)
    try: wait(lambda:paste()==b'FOOTCLIPBOARD')
    except Exception:
        print('FOOT DEBUG',repr(paste()),cmd(['wl-paste','-n','--primary']).stdout,flush=True)
        raise
    assert cmd(['wl-paste','-n','--primary']).stdout==b'FOOTCLIPBOARD'
    results['foot_mouse_selection_both_clipboards']=True
    terminal.terminate();terminal.wait()
    # Screenshot command copies an actual PNG into the desktop/history.
    for name in ('swappy','notify-send'):
        stub=home/'.local/bin'/name;stub.write_text('#!/bin/sh\nexit 0\n');stub.chmod(0o755)
    env['XDG_PICTURES_DIR']=str(b/'pictures')
    cmd([str(ROOT/'alpine/desktop/.local/bin/oldbook-screenshot'),'full'],check=True)
    screenshot=next((b/'pictures/Screenshots').glob('*.png'))
    assert cmd(['wl-paste','-n','-t','image/png']).stdout==screenshot.read_bytes()
    results['screenshot_copies_png']=True
    # Capture the production picker with synthetic history, then cancel it.
    picker.unlink();picker.symlink_to(ROOT/'alpine/desktop/.local/bin/oldbook-fuzzel')
    copy(b'Synthetic clipboard demo: text, screenshots, terminal selections')
    wait(lambda:b'Synthetic clipboard demo' in listing())
    menu=start([str(HELPER),'pick'])
    time.sleep(1.5)
    assert menu.poll() is None
    cmd(['grim',str(OUT/'history-menu.png')],check=True)
    cmd(['wtype','-k','Escape'],check=True)
    wait(lambda:menu.poll() is not None)
    assert paste()==b'Synthetic clipboard demo: text, screenshots, terminal selections'
    results['real_history_menu_cancel_preserves_clipboard']=True
    (OUT/'runtime-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2),flush=True)
finally:
    if 'socket' in globals():
        cmd(['tmux','-S',socket,'kill-server'])
    for p in reversed(processes):
        if p.poll() is None:p.terminate()
    for p in reversed(processes):
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    (OUT/'runtime-results.json').write_text(json.dumps(results,indent=2)+'\n')
    log.close()
    temp.cleanup()
