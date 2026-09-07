import json,os,subprocess,tempfile,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='expo-check-') as temp:
    base=Path(temp);runtime=base/'run';runtime.mkdir(mode=0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1')
    for name in ('SWAYSOCK','WAYLAND_DISPLAY','DISPLAY'):env.pop(name,None)
    config=base/'sway.conf';config.write_text('output HEADLESS-1 mode 1440x900\noutput * bg #1d2021 solid_color\nseat seat0 fallback true\ninclude '+str(repo/'alpine/desktop/.config/sway/gestures.conf')+'\n')
    processes=[]
    with (base/'run.log').open('w') as log:
        sway=subprocess.Popen(['sway','-c',str(config)],env=env,stdout=log,stderr=log);processes.append(sway)
        try:
            for _ in range(60):
                displays=[p for p in runtime.glob('wayland-*') if p.is_socket()]
                sockets=list(runtime.glob('sway-ipc*.sock'))
                if displays and sockets:break
                time.sleep(.1)
            env.update(WAYLAND_DISPLAY=displays[0].name,SWAYSOCK=str(sockets[0]))
            def command(text):return subprocess.run(['swaymsg','-s',str(sockets[0]),text],env=env,capture_output=True,text=True,check=True)
            for workspace,title in ((1,'Terminal'),(2,'Fossil review')):
                command('workspace number '+str(workspace))
                client=subprocess.Popen(['foot','--title='+title,'-e','cat'],env=env,stdout=log,stderr=log);processes.append(client);time.sleep(.4)
            command('workspace number 1')
            def launch():
                p=subprocess.Popen([str(repo/'alpine/desktop/.local/bin/oldbook-expo'),'show'],env=env,stdout=log,stderr=log);processes.append(p);time.sleep(1)
                if p.poll() is not None:raise RuntimeError((base/'run.log').read_text())
                return p
            # A headless seat needs a keyboard before GTK maps its exclusive layer.
            keyboard=subprocess.Popen(['wtype','-s','2000','-k','2','-s','2500','Terminal','-s','300','-k','Return','-s','30000'],env=env,stdout=log,stderr=log);processes.append(keyboard)
            time.sleep(.2)
            expo=launch()
            subprocess.run(['grim',str(repo/'alpine/verification/gestures/expo.png')],env=env,check=True)
            expo.wait(timeout=5)
            workspaces=json.loads(subprocess.check_output(['swaymsg','-s',str(sockets[0]),'-t','get_workspaces','-r'],env=env))
            assert next(w['num'] for w in workspaces if w['focused'])==2
            expo=launch()
            expo.wait(timeout=5)
            workspaces=json.loads(subprocess.check_output(['swaymsg','-s',str(sockets[0]),'-t','get_workspaces','-r'],env=env))
            assert next(w['num'] for w in workspaces if w['focused'])==1
            expo=launch()
            subprocess.run([str(repo/'alpine/desktop/.local/bin/oldbook-expo'),'close'],env=env,check=True)
            expo.wait(timeout=5)
            code = """import sys, gi
sys.path.insert(0, sys.argv[1])
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk, GLib
import expo
original_main = Gtk.main
def main():
    def swipe():
        window = Gtk.Window.list_toplevels()[0]
        for phase in (Gdk.TouchpadGesturePhase.BEGIN, Gdk.TouchpadGesturePhase.UPDATE, Gdk.TouchpadGesturePhase.END):
            event = Gdk.Event.new(Gdk.EventType.TOUCHPAD_SWIPE)
            event.touchpad_swipe.phase = phase
            event.touchpad_swipe.n_fingers = 3
            event.touchpad_swipe.dx = 0
            event.touchpad_swipe.dy = 80
            window.emit('event', event)
        return False
    GLib.timeout_add(500, swipe)
    original_main()
Gtk.main = main
expo.main('show')
"""
            gesture=subprocess.Popen(['python3','-c',code,str(repo/'alpine/desktop/.local/lib/oldbook')],env=env,stdout=log,stderr=log)
            processes.append(gesture)
            assert gesture.wait(timeout=5)==0
            print(json.dumps({'search_focuses_window':True,'gtk_down_swipe_closes':True,'overview_rendered' :True,'keyboard_workspace_selection':True,'close_command':True,'gesture_config_loaded':True}))
        except Exception:
            print((base/'run.log').read_text()[-4000:]);raise
        finally:
            for p in reversed(processes):
                if p.poll() is None:p.terminate()
            for p in reversed(processes):
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
