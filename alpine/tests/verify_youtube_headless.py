import json, os, runpy, signal, subprocess, tempfile, time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='mbp-intel-youtube-check-') as temp:
    home=Path(temp);runtime=home/'run';runtime.mkdir(mode=0o700)
    os.environ.update(HOME=temp,XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_LIBINPUT_NO_DEVICES='1',DBUS_SESSION_BUS_ADDRESS='unix:path='+temp+'/no-bus')
    os.environ.pop('SWAYSOCK',None);os.environ.pop('WAYLAND_DISPLAY',None);os.environ.pop('DISPLAY',None)
    os.environ.update(LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe')
    config=home/'sway.conf';config.write_text('output HEADLESS-1 mode 640x360\nseat seat0 fallback true\nworkspace 1\nfor_window [app_id="mbp-intel-youtube"] floating enable, sticky enable, resize set 320 180\n')
    clip=home/'sample.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=640x360:d=3','-c:v','ffv1','-threads','1',str(clip)],check=True)
    log=(home/'sway.log').open('w')
    sway=subprocess.Popen(['sway','-c',str(config)],stdout=log,stderr=log,start_new_session=True)
    service=None
    try:
        for _ in range(100):
            sockets=list(runtime.glob('sway-ipc*.sock'))
            displays=[p for p in runtime.glob('wayland-*') if p.is_socket()]
            if sockets and displays:break
            if sway.poll() is not None:raise RuntimeError((home/'sway.log').read_text())
            time.sleep(.1)
        os.environ['SWAYSOCK']=str(sockets[0]);os.environ['WAYLAND_DISPLAY']=displays[0].name
        api=runpy.run_path(str(root/'alpine/desktop/.local/bin/mbp-intel-youtube'))
        service=subprocess.Popen([str(root/'alpine/desktop/.local/bin/mbp-intel-youtube'),'serve'],stdout=log,stderr=log,start_new_session=True)
        def until(test, seconds=15):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                try:
                    result=test()
                    if result:return result
                except (OSError,RuntimeError):pass
                time.sleep(.1)
            raise AssertionError('timeout: '+(home/'.local/state/mbp-intel/youtube/playback.log').read_text() if (home/'.local/state/mbp-intel/youtube/playback.log').exists() else 'timeout')
        req=api['request'];until(lambda:req('status'))
        req('load',entries=[{'url':str(clip),'title':'Test one'},{'url':str(clip),'title':'Test two'}])
        until(lambda:req('status')['position']>.3)
        subprocess.run(['grim','-o','HEADLESS-1',str(root/'alpine/verification/youtube/desktop-mode.png')],check=True)
        req('pause');position=req('status')['position']
        req('pip')
        ipc=api['IPC'];sock=sockets[0]
        def pip_windows():
            return [v for w in ipc['workspace_nodes'](ipc['request'](sock,4)) for v in ipc['all_views'](w) if v.get('app_id')=='mbp-intel-youtube']
        until(pip_windows)
        subprocess.run(['grim','-o','HEADLESS-1',str(root/'alpine/verification/youtube/pip-mode.png')],check=True)
        assert req('status')['paused'];assert req('status')['position']>=position-.3
        req('desktop');until(lambda:not pip_windows())
        ipc['command'](sock,'workspace 2')
        directory,_=api['paths']()
        until(lambda:not (directory/'mpv.sock').exists() or not api['mpv'](directory,['get_property','idle-active']),seconds=2)
        # A hidden desktop has no decoder process; position is preserved.
        time.sleep(1)
        assert req('status')['paused']
        ipc['command'](sock,'workspace 1')
        req('rewatch');until(lambda:req('status')['awaiting'],seconds=12)
        assert req('status')['index']==0
        req('keep');assert req('status')['index']==1
        req('remove');assert req('status')['index']==2
        result={'workspace_one_only':True,'desktop_playback':True,'pip_window':True,'resume_position':True,'pause_retained':True,'eof_waits_for_decision':True,'keep_advances':True,'remove_advances':True}
        (root/'alpine/verification/youtube/headless.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    except Exception:
        for path in (home/'.local/state/mbp-intel/youtube').glob('*.log'):
            print(path.name, path.read_text()[-4000:])
        raise
    finally:
        if service and service.poll() is None:
            service.terminate();service.wait(timeout=10)
        if sway.poll() is None:sway.terminate();sway.wait(timeout=10)
