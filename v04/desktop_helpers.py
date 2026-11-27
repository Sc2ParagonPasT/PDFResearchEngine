"""Desktop preferences and Windows-safe export naming; no document parsing."""
import json
import os
import re
import tempfile
from pathlib import Path

def documents_folder():
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            from uuid import UUID
            class GUID(ctypes.Structure):
                _fields_=[('bytes',ctypes.c_ubyte*16)]
            guid=GUID.from_buffer_copy(UUID('FDD39AD0-238F-46AF-ADB4-6C85480369C7').bytes_le)
            ptr=ctypes.c_wchar_p()
            sh=ctypes.windll.shell32.SHGetKnownFolderPath
            sh.argtypes=[ctypes.POINTER(GUID),wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_wchar_p)]
            sh.restype=ctypes.c_long
            if sh(ctypes.byref(guid),0,None,ctypes.byref(ptr))==0:
                try:
                    if ptr.value and Path(ptr.value).is_dir(): return Path(ptr.value)
                finally: ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(ptr,ctypes.c_void_p))
        except (OSError,AttributeError,ValueError): pass
    p=Path.home()/'Documents'
    return p if p.is_dir() else Path.home()

def export_folder(value):
    try:
        p=Path(value).expanduser()
        if value and p.is_absolute() and p.is_dir(): return p
    except (OSError,TypeError,ValueError): pass
    return documents_folder()

def safe_pdf_name(title, folder, suffix=''):
    """Filename component only, bounded UTF-16 length and conservative Windows path."""
    name=re.sub(r'[\x00-\x1f<>:"/\\|?*]', ' ', str(title or ''))
    name=' '.join(name.split()).strip(' .')
    if name.lower().endswith('.pdf'): name=name[:-4].rstrip(' .')
    if not name: name='Research document'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]|CONIN\$|CONOUT\$)',name.split('.')[0].rstrip()): name='_'+name
    tail=suffix+'.pdf'
    units=lambda v:len(str(v).encode('utf-16-le',errors='replace'))//2
    budget=min(180,240-units(Path(folder).absolute())-1)-units(tail)
    if budget<12: raise ValueError('Export folder path is too long; select a shorter folder.')
    while units(name)>budget: name=name[:-1]
    return (name.rstrip(' .') or 'Document')+tail

def unique_pdf_path(folder,title):
    folder=Path(folder)
    if not folder.is_dir(): raise ValueError('Export folder is unavailable')
    for i in range(1,10001):
        candidate=folder/safe_pdf_name(title,folder,'' if i==1 else ' ('+str(i)+')')
        if not candidate.exists() and not candidate.is_symlink():return candidate
    raise ValueError('Too many files with this title')

def load_preferences(path):
    try:
        v=json.loads(Path(path).read_text(encoding='utf-8'))
        return v if isinstance(v,dict) else {}
    except (OSError,ValueError): return {}

def save_preferences(path,values):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.preferences-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(values,f,indent=2)
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)
