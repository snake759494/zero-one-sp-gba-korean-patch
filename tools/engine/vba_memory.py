"""VBA process debugging only. No keyboard, mouse, window messages or focus changes."""
import ctypes as C, struct, json, hashlib, time, sys
from ctypes import wintypes as W
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
k=C.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p]
k.WriteProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p]
k.CloseHandle.argtypes=[W.HANDLE]
k.VirtualProtectEx.argtypes=[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,C.POINTER(W.DWORD)]
class VBA:
    def __init__(self):
        expected=str(ROOT.parent/'vba.exe').lower()
        pp=[p for p in psutil.process_iter(['pid','exe']) if (p.info['exe'] or '').lower()==expected]
        if len(pp)!=1:raise RuntimeError('Expected exactly one workspace VBA process')
        self.pid=pp[0].pid; self.h=k.OpenProcess(0x38,False,self.pid)
        if not self.h:raise OSError(C.get_last_error())
    def read(self,a,n):
        b=C.create_string_buffer(n)
        if not k.ReadProcessMemory(self.h,a,b,n,None):raise OSError(C.get_last_error(),hex(a))
        return b.raw
    def write(self,a,b):
        v=C.create_string_buffer(b)
        if not k.WriteProcessMemory(self.h,a,v,len(b),None):raise OSError(C.get_last_error())
    def close(self):k.CloseHandle(self.h)
    def capture(self,name):
        from PIL import Image
        p=struct.unpack('<I',self.read(0x604f14,4))[0]
        b=self.read(p,156168)
        path=ROOT/(name+'.png')
        Image.frombytes('RGB',(241,162),b,'raw','BGRX').crop((0,1,240,161)).save(path)
        return path
    def press(self,key,seconds=.12):
        # Instrument this exact emulator's input callback in process memory.
        # The executable on disk and all Windows input remain untouched.
        exe=ROOT.parent/'vba.exe'
        assert hashlib.sha256(exe.read_bytes()).hexdigest()=='4b84f92cc67a278488de336adc45ae55d309b2dac9c7aed187d7a6d25a54f35e'
        patches=[]
        for addr,value in [(0x50e740,1),(0x50e770,key)]:
            original=self.read(addr,6)
            disk=exe.read_bytes()[addr-0x400000:addr-0x400000+6]
            neutral=b'\xb8'+struct.pack('<I',1 if addr==0x50e740 else 0)+b'\xc3'
            assert original in [disk,neutral]
            old=W.DWORD()
            if not k.VirtualProtectEx(self.h,addr,6,0x40,C.byref(old)):raise OSError(C.get_last_error())
            patches.append((addr,original,old.value,value))
        try:
            for addr,original,old,value in patches:self.write(addr,b'\xb8'+struct.pack('<I',value)+b'\xc3')
            # Hidden rendering can be slow. Confirm the GBA actually sampled
            # the press instead of relying only on a short wall-clock delay.
            deadline=time.monotonic()+10
            expected=0x03ff^(key&0x03ff)
            while struct.unpack('<H',self.read(0x581fe4,2))[0]!=expected:
                if time.monotonic()>deadline:raise TimeoutError('GBA did not sample input')
                time.sleep(.02)
            time.sleep(max(seconds,.2))
            self.write(0x50e770,b'\xb8'+struct.pack('<I',0)+b'\xc3')
            deadline=time.monotonic()+10
            while struct.unpack('<H',self.read(0x581fe4,2))[0]!=0x03ff:
                if time.monotonic()>deadline:raise TimeoutError('GBA did not sample release')
                time.sleep(.02)
        finally:
            for addr,original,old,value in reversed(patches):
                self.write(addr,original);unused=W.DWORD();k.VirtualProtectEx(self.h,addr,6,old,C.byref(unused))
        time.sleep(.35)
    def neutral(self):
        # Isolate game input from the user's keyboard for the rest of this QA
        # process. These hooks disappear when the emulator exits.
        for addr,value in [(0x50e740,1),(0x50e770,0)]:
            disk=(ROOT.parent/'vba.exe').read_bytes()[addr-0x400000:addr-0x400000+6]
            assert self.read(addr,6)==disk
            old=W.DWORD();assert k.VirtualProtectEx(self.h,addr,6,0x40,C.byref(old))
            self.write(addr,b'\xb8'+struct.pack('<I',value)+b'\xc3')
            unused=W.DWORD();k.VirtualProtectEx(self.h,addr,6,old.value,C.byref(unused))
    def map(self):
        b=self.read(0x600000,0x180000)
        for i in range(0,len(b)-80,4):
            if struct.unpack_from('<I',b,i+4)[0]!=0x3ffff:continue
            if struct.unpack_from('<I',b,i+12)[0]!=0x7fff:continue
            if struct.unpack_from('<I',b,i+20)[0]!=0x3ff:continue
            if struct.unpack_from('<I',b,i+28)[0]!=0x3ff:continue
            addr=0x600000+i-16
            return addr,[struct.unpack_from('<II',self.read(addr+8*j,8)) for j in range(16)]
        raise RuntimeError('VBA memory map not found')
if __name__=='__main__':
    v=VBA()
    try:
        if len(sys.argv)>1:
            if sys.argv[1]=='capture':print(v.capture(sys.argv[2]))
            elif sys.argv[1]=='press':v.press(int(sys.argv[2],0),float(sys.argv[3]) if len(sys.argv)>3 else .12)
            elif sys.argv[1]=='neutral':v.neutral()
            else:raise ValueError('action')
            sys.exit()
        a,m=v.map();print(hex(a),[(hex(p),hex(mask)) for p,mask in m])
        (ROOT/'vba_memory_map.json').write_text(json.dumps({'pid':v.pid,'address':a,'map':m},indent=2))
        print('ROM header:',v.read(m[8][0]+0xa0,32))
    finally:v.close()
