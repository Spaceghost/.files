#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parent
ROOT = Path('/home/jack/.files')
OUT = BASE / 'evidence'
OUT.mkdir(exist_ok=False)
report = {'host_changes': 0, 'status': 'running', 'checks': [], 'phases': []}
report['module_sha256'] = hashlib.sha256(Path('/usr/lib/waybar/oldbook-art.so').read_bytes()).hexdigest()
report['style_sha256'] = hashlib.sha256(Path('/home/jack/.config/waybar/style.css').read_bytes()).hexdigest()
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0'], text=True))
subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(BASE/'inspect.c'), '-o', str(BASE/'inspect.so'), '-ldl', *flags], check=True)

def wait(fn, message, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = fn()
        if value: return value
        time.sleep(.05)
    raise RuntimeError(message)

with tempfile.TemporaryDirectory(prefix='waybar-freeze-private-') as directory:
    private = Path(directory)
    env = dict(os.environ)
    for key, folder in [('HOME','home'),('XDG_RUNTIME_DIR','run'),('XDG_CONFIG_HOME','config'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data')]:
        target = private/folder; target.mkdir(mode=0o700); env[key] = str(target)
    for key in ('SWAYSOCK','WAYLAND_DISPLAY','DISPLAY','DBUS_SESSION_BUS_ADDRESS','LD_PRELOAD'):
        env.pop(key, None)
    env.update(WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_HEADLESS_OUTPUTS='1',NO_AT_BRIDGE='1',GTK_USE_PORTAL='0')
    runtime = Path(env['XDG_RUNTIME_DIR'])
    style_dir = Path(env['XDG_CONFIG_HOME'])/'waybar'; style_dir.mkdir()
    style = style_dir/'style.css'
    style.write_text(Path('/home/jack/.config/waybar/style.css').read_text())
    state = style_dir/'waybar-state.css'
    state.write_text('window#waybar.top #clock.module { color: #ff0000; }\n')
    art = private/'art-status'
    art.write_text("#!/bin/sh\nprintf '%s\\n' '{\"text\":\"ART\",\"tooltip\":\"Private fixture\"}'\n"); art.chmod(0o755)
    cfg = style_dir/'config.jsonc'
    cfg.write_text(json.dumps({'name':'top','height':32,'position':'top','reload_style_on_change':True,'modules-left':['cffi/art','sway/workspaces'],'modules-right':['clock'],'cffi/art':{'module_path':'/usr/lib/waybar/oldbook-art.so','command':str(art)},'sway/workspaces':{'format':'{value}','disable-markup':True},'clock':{'format':'{:%H:%M:%S}','interval':1}}))
    sway_config = OUT/'sway.conf'
    sway_config.write_text('xwayland disable\noutput HEADLESS-1 mode 1440x480\noutput * bg #13091f solid_color\nseat seat0 fallback true\nfocus_follows_mouse no\n')
    busconfig = private/'bus.conf'
    busconfig.write_text('<busconfig><type>session</type><listen>unix:path='+str(runtime/'bus')+'</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
    log = (OUT/'runtime.log').open('w')
    processes = []
    def spawn(args, local_env=None):
        process = subprocess.Popen(args, env=local_env or env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        processes.append(process); return process
    def command(text):
        result = subprocess.run(['swaymsg','-r',text],env=env,capture_output=True,text=True,check=True,timeout=3)
        assert all(item.get('success') for item in json.loads(result.stdout)), result.stdout
    observation = OUT/'observation.json'
    def observe():
        try:return json.loads(observation.read_text())
        except (FileNotFoundError,json.JSONDecodeError):return None
    def ticks():
        data = Path(f'/proc/{bar.pid}/stat').read_text().rsplit(') ',1)[1].split()
        return int(data[11])+int(data[12])
    def phase(name, seconds=3):
        first = observe(); start = time.monotonic(); initial = ticks(); samples=[]
        while time.monotonic()-start<seconds:
            samples.append(observe());time.sleep(.2)
        final = observe(); elapsed = time.monotonic()-start
        entry={'name':name,'elapsed':round(elapsed,3),'cpu_percent':round(100*(ticks()-initial)/os.sysconf('SC_CLK_TCK')/elapsed,2),'first':first,'last':final,'samples':samples}
        report['phases'].append(entry)
        assert final['beats']>first['beats'] and final['clock']!=first['clock'], entry
        return entry
    try:
        bus=spawn(['dbus-daemon','--nofork','--config-file='+str(busconfig)])
        wait(lambda:(runtime/'bus').is_socket(),'private bus missing')
        env['DBUS_SESSION_BUS_ADDRESS']='unix:path='+str(runtime/'bus')
        sway=spawn(['swayfx','-c',str(sway_config)])
        env['SWAYSOCK']=str(wait(lambda:next(runtime.glob('sway-ipc*.sock'),None),'private sway missing'))
        env['WAYLAND_DISPLAY']=wait(lambda:next((p.name for p in runtime.glob('wayland-*') if p.is_socket()),None),'private Wayland missing')
        foot_config=private/'foot.ini';foot_config.write_text('[main]\nfont=monospace:size=10\n')
        for number in range(1,5):
            command('workspace number '+str(number))
            spawn(['foot','--config='+str(foot_config),'--app-id=title-fixture-'+str(number),'-e','python3','-c',"import os,time; from pathlib import Path; p=Path(os.environ['XDG_STATE_HOME'])/'titles-running'; n=0\nwhile True:\n if p.exists():\n  print('\\033]2;private-title-'+str(n)+'\\007',end='',flush=True); n+=1\n time.sleep(.1)"])
            time.sleep(.25)
        bar_env=dict(env,LD_PRELOAD=str(BASE/'inspect.so'),OLDBOOK_PRIVATE_WAYBAR_INSPECTION=str(observation))
        bar=spawn(['waybar','-l','debug','-c',str(cfg),'-s',str(style)],bar_env)
        wait(lambda:observe() and observe()['clock'],'clock did not appear')
        wait(lambda:observe()['color']==[1,0,0], 'initial red inspection rule did not apply')
        phase('idle-before-style-changes')
        report['css_changes']=[]
        for name,color in [('green','#00ff00'),('blue','#0000ff'),('red','#ff0000')]:
            initial=observe();temporary=state.with_name('waybar-state.css.atomic.tmp');temporary.write_text('window#waybar.top #clock.module { color: '+color+'; }\n');temporary.replace(state)
            expected={'green':[0,1,0],'blue':[0,0,1],'red':[1,0,0]}[name]
            result=wait(lambda:(value if (value:=observe()) and value['color']==expected else None),'atomic imported style did not update '+name)
            report['css_changes'].append({'color':name,'before':initial,'after':result})
        report['checks'].append('three-atomic-imported-css-changes-update-without-signal')
        phase('idle-after-style-changes')
        running=Path(env['XDG_STATE_HOME'])/'titles-running';running.touch()
        phase('four-terminal-titles-at-ten-hz',5)
        running.unlink()
        phase('idle-after-title-stream')
        for _ in range(3):
            os.kill(bar.pid,signal.SIGUSR2);time.sleep(.5)
        phase('after-three-explicit-sigusr2-reloads')
        report['checks'].append('clock-and-main-loop-remain-live-in-all-phases')
        report['status']='passed'
    except BaseException as error:
        report['status']='failed';report['error']=str(error);raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=3)
                except (ProcessLookupError,subprocess.TimeoutExpired):
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait()
        log.close();(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(OUT)
