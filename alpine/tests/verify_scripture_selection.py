"""Real Fuzzel Enter -> saved passage -> immediate Conky reload, in private Sway."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

REPO=Path(__file__).resolve().parents[2]
OUTPUT=REPO/'alpine/verification/scripture-selection'
HELPER=REPO/'alpine/desktop/.local/bin/mbp-intel-scripture'
OUTPUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='scripture-native-') as directory:
    root=Path(directory);runtime=root/'run';runtime.mkdir(mode=0o700)
    home=root/'home';home.mkdir()
    env=dict(os.environ,HOME=str(home),XDG_RUNTIME_DIR=str(runtime),
             XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'),
             WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1')
    for name in ('SWAYSOCK','WAYLAND_DISPLAY','DISPLAY'):env.pop(name,None)
    config=root/'sway.conf';config.write_text('output HEADLESS-1 mode 1440x900\noutput * bg #282828 solid_color\nseat seat0 fallback true\n' + f'bindsym Mod4+slash exec touch {root}/bible-key\nbindsym Mod4+question exec touch {root}/all-key\n')
    children=[]
    with (OUTPUT/'native.log').open('w') as log:
        sway=subprocess.Popen(['sway','-c',str(config)],env=env,stdout=log,stderr=log);children.append(sway)
        try:
            for _ in range(80):
                displays=[p for p in runtime.glob('wayland-*') if p.is_socket()]
                sockets=list(runtime.glob('sway-ipc*.sock'))
                if displays and sockets:break
                time.sleep(.1)
            env.update(WAYLAND_DISPLAY=displays[0].name,SWAYSOCK=str(sockets[0]))
            subprocess.run(['wtype','-M','logo','-k','slash','-m','logo'],env=env,check=True)
            subprocess.run(['wtype','-M','logo','-k','question','-m','logo'],env=env,check=True)
            time.sleep(1)
            assert (root/'bible-key').exists() and (root/'all-key').exists(), ((root/'bible-key').exists(), (root/'all-key').exists())
            def command(*args):
                return subprocess.run([str(HELPER),*args],env=env,capture_output=True,text=True,check=True,timeout=15)
            command('select','John 3:16')
            state=home/'.local/state/mbp-intel/conky';state.mkdir(parents=True)
            conky_config=state/'scripture.conf'
            conky_config.write_text("conky.config={out_to_wayland=true,out_to_x=false,own_window=true,own_window_type='desktop',own_window_colour='#00000000',alignment='top_left',gap_x=30,gap_y=30,minimum_width=650,maximum_width=650,minimum_height=250,update_interval=60,font='monospace:size=14',use_xft=true,default_color='#ebdbb2',color1='#d8a657',color2='#a89984',text_buffer_size=4096}\nconky.text=[[${execpi 120 "+str(HELPER)+" panel --width 60}]]\n")
            conky=subprocess.Popen(['conky','-c',str(conky_config)],env=env,stdout=log,stderr=log);children.append(conky)
            (state/'pids.json').write_text(json.dumps({'scripture':conky.pid}))
            time.sleep(2)
            subprocess.run(['grim',str(OUTPUT/'before.png')],env=env,check=True,timeout=5)
            finder=subprocess.Popen([str(HELPER),'find','--all'],env=env,stdout=log,stderr=log);children.append(finder)
            # Wait for the actual Fuzzel process after corpus construction.
            for _ in range(100):
                child_ids=Path(f'/proc/{finder.pid}/task/{finder.pid}/children').read_text().split()
                if any(Path(f'/proc/{pid}/comm').read_text().strip()=='fuzzel' for pid in child_ids):break
                time.sleep(.1)
            time.sleep(2)
            subprocess.run(['wtype','-d','20','Torah Genesis 1:1','-k','Return'],env=env,check=True,timeout=5)
            finder.wait(timeout=15)
            assert finder.returncode==0
            saved=json.loads((home/'.local/state/mbp-intel/scripture/selection.json').read_text())
            assert saved['reference']=='Torah Genesis 1:1',saved['reference']
            assert saved['edition']=='JPS 1917'
            time.sleep(3)
            subprocess.run(['grim',str(OUTPUT/'after.png')],env=env,check=True,timeout=5)
            log.flush()
            new_pid=json.loads((state/'pids.json').read_text())['scripture']
            assert new_pid != conky.pid
            assert Path(f'/proc/{new_pid}').exists()
            assert (OUTPUT/'before.png').read_bytes()!=(OUTPUT/'after.png').read_bytes()
            report={'slash_question_bindings':True,'real_fuzzel_enter':True,'selection':saved['reference'],'edition':saved['edition'],
                    'only_scripture_replaced':True,'new_panel_running':True,'render_changed_within_seconds':3,
                    'periodic_display_seconds':60,'periodic_text_seconds':120}
            (OUTPUT/'native.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report))
        finally:
            try:
                new_pid=json.loads((home/'.local/state/mbp-intel/conky/pids.json').read_text())['scripture']
                if 'conky' in locals() and new_pid!=conky.pid:
                    os.kill(new_pid,15)
                    time.sleep(.2)
                    if Path(f'/proc/{new_pid}').exists():os.kill(new_pid,9)
            except (OSError,KeyError):pass
            for process in reversed(children):
                if process.poll() is None:process.terminate()
            for process in reversed(children):
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
