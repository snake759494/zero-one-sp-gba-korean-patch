"""Background-only exact-build UI smoke test. Always terminate own VBA in finally."""
from pathlib import Path
from datetime import date
import subprocess,time,struct,json,hashlib,psutil
from PIL import Image,ImageChops,ImageStat
from vba_memory import VBA,k,W
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent

def main():
    ini=BASE/'vba.ini';original_ini=ini.read_bytes();backup=ROOT/'vba_qa_original.ini';backup.write_bytes(original_ini)
    rom=BASE/'Zero One SP (Korean).gba';data=rom.read_bytes();build=json.loads((ROOT/'build_report.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(data).hexdigest()==build['output_sha256']
    battery=rom.with_suffix('.sav');battery_before=battery.read_bytes() if battery.exists() else None
    proc=None;v=None;shots=[];binding={}
    try:
        ini.write_bytes(original_ini.replace(b'pauseWhenInactive=1',b'pauseWhenInactive=0').replace(b'filter=8',b'filter=0'))
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        proc=subprocess.Popen([str(BASE/'vba.exe'),str(rom)],cwd=BASE,startupinfo=startup,creationflags=0x4)
        v=VBA();assert v.pid==proc.pid;v.neutral()
        # Install private input callbacks before the emulator executes any code.
        k.OpenThread.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenThread.restype=W.HANDLE
        k.ResumeThread.argtypes=[W.HANDLE];k.ResumeThread.restype=W.DWORD
        thread=k.OpenThread(0x2,False,psutil.Process(proc.pid).threads()[0].id)
        if not thread:raise RuntimeError('Cannot open suspended VBA thread')
        try:assert k.ResumeThread(thread)!=0xffffffff
        finally:k.CloseHandle(thread)
        deadline=time.monotonic()+30
        while True:
            try:_,mapping=v.map();break
            except RuntimeError:
                if proc.poll() is not None or time.monotonic()>=deadline:raise
                time.sleep(.5)
        def capture(name):
            path=v.capture(name);shots.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rom_sha256':build['output_sha256']})
        def frame():
            pointer=struct.unpack('<I',v.read(0x604f14,4))[0]
            return Image.frombytes('RGB',(241,162),v.read(pointer,156168),'raw','BGRX').crop((0,1,240,161))
        def settle(seconds=.5):v.press(1024,seconds)
        def wait_screen(expected_path,box,attempts=10):
            expected=Image.open(expected_path).convert('RGB').crop(box)
            for _ in range(attempts):
                actual=frame().crop(box)
                difference=sum(ImageStat.Stat(ImageChops.difference(actual,expected)).mean)/3
                if difference<14:return difference
                settle(.6)
            capture('qa_current_wait_failure')
            raise TimeoutError(f'Expected screen did not settle: {expected_path.name}, difference={difference}')
        # Catch the first title frame without turbo or pre-start user input.
        expected=Image.open(ROOT/'graphics_review/korean_00BC3114.png').convert('RGB').crop((0,20,240,108))
        deadline=time.monotonic()+50
        last_skip=time.monotonic()
        while True:
            try:
                actual=frame().crop((0,20,240,108))
                if sum(ImageStat.Stat(ImageChops.difference(actual,expected)).mean)/3<14:break
            except OSError:pass
            if time.monotonic()>deadline:
                capture('qa_current_initial_failure');raise TimeoutError('Initial title did not appear')
            if time.monotonic()-last_skip>2:
                v.press(8,.2);last_skip=time.monotonic()
            time.sleep(.05)
        capture('qa_current_boot')
        v.press(8,.3);settle(.3);v.press(1,.3);settle(.3);capture('qa_current_menu')
        def orange_count(box):return sum(r>180 and 85<g<220 and b<140 for r,g,b in frame().crop(box).getdata())
        for key in (16,128,64,32):
            v.press(key,.3);settle(.3)
            if orange_count((128,112,192,128))>80:break
        else:raise RuntimeError('Settings button selection failed')
        capture('qa_current_settings_selected')
        v.press(1,.3);settle(.8)
        wait_screen(ROOT/'graphics_review/korean_00BC117C.png',(0,0,240,28))
        capture('qa_current_options')
        for row in range(5):
            v.press(128,.3);settle(.3);capture(f'qa_option_selection_{row+1}')
        # Vertical selection clamps at the last row rather than wrapping.
        for _ in range(5):v.press(64,.3);settle(.2)
        for speed,key in enumerate((32,32,32,16,16,16),1):
            v.press(key,.3);settle(.3);capture(f'qa_option_speed_{speed}')
        v.press(2,.3);settle(.6)
        wait_screen(ROOT/'graphics_review/korean_00BC3114.png',(0,20,240,108))
        capture('qa_current_return_from_options')
        # Repeat the round trip to expose stale VRAM or cached-map damage.
        v.press(1,.3);settle(.8)
        wait_screen(ROOT/'graphics_review/korean_00BC117C.png',(0,0,240,28))
        v.press(2,.3);settle(.6)
        wait_screen(ROOT/'graphics_review/korean_00BC3114.png',(0,20,240,108))
        capture('qa_current_return_again')
        for key in (32,64,16,128):
            v.press(key,.3);settle(.2)
            if orange_count((48,112,112,128))>80:break
        else:raise RuntimeError('Play button selection failed')
        v.press(1,.3);settle(.8)
        wait_screen(ROOT/'graphics_review/korean_00BC3114.png',(0,20,240,108))
        capture('qa_current_mode')
        for i in range(4):
            v.press(1,.3);settle(.2);capture(f'qa_current_start_{i}')
        for i in range(3):
            v.press(1026,.4);time.sleep(.5);capture(f'qa_current_story_{i}')
        evidence=ROOT/'analysis_evidence';evidence.mkdir(exist_ok=True)
        prefix=build['output_sha256'][:8]
        for region,size in [(4,0x400),(5,0x400),(6,0x18000),(7,0x400)]:
            (evidence/f'name_probe_{prefix}_region{region}.bin').write_bytes(v.read(mapping[region][0],size))
        actual=v.read(mapping[8][0],build['used_size']);assert actual==data[:build['used_size']]
        binding={'date':date.today().isoformat(),'file_sha256':build['output_sha256'],'used_region_sha256':hashlib.sha256(actual).hexdigest(),
                 'used_region_equal':True,'used_size':build['used_size'],'pid':proc.pid,'vba_sha256':hashlib.sha256((BASE/'vba.exe').read_bytes()).hexdigest()}
    finally:
        if v:v.close()
        if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=10)
        if battery_before is not None:battery.write_bytes(battery_before)
        ini.write_bytes(original_ini);backup.unlink(missing_ok=True)
        if binding:
            binding['emulator_closed']=True
            (ROOT/'runtime_binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'qa_current_capture_report.json').write_text(json.dumps({'rom_sha256':build['output_sha256'],'screenshots':shots,'emulator_closed':True,'settings_restored':True},ensure_ascii=False,indent=2),encoding='utf-8')
        print('VBA closed; settings restored; screenshots',len(shots))
if __name__=='__main__':main()
