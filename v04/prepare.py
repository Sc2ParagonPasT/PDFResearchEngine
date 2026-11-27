"""Apply v0.4 desktop overlay over the known v0.3 baseline. Fail on unexpected anchors."""
import sys, shutil, subprocess
from pathlib import Path

root=Path(sys.argv[1])
here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'v03'/'prepare.py'),str(root)],check=True)
subprocess.run([sys.executable,str(here.parent/'tools'/'apply-clam-temp-fix.py'),str(root)],check=True)
shutil.copyfile(here.parent/'patches'/'diagnostics.py',root/'diagnostics.py')
for name in ('desktop_helpers.py','desktop_v04.py','test_desktop_v04.py'):
    shutil.copyfile(here/name,root/name)
def change(s,a,b):
    if s.count(a)!=1:raise RuntimeError('Expected one anchor: '+a[:100])
    return s.replace(a,b)
p=root/'app.py';s=p.read_text(encoding='utf-8')
s=change(s,'shell=ttk.Frame(self.win,padding=18)','shell=ttk.Frame(getattr(self,"content_parent",self.win),padding=18)')
s=change(s,"root=tk.Tk()\n        try:\n            with single_instance(ROOT):App(root).win.mainloop()","root=tk.Tk()\n        from desktop_v04 import desktop_class\n        try:\n            with single_instance(ROOT):desktop_class(App)(root).win.mainloop()")
s=s.replace('v0.3','v0.4')
p.write_text(s,encoding='utf-8')
p=root/'security.py';s=p.read_text(encoding='utf-8')
s=change(s,"def reconstruct(src,dest):","def reconstruct(src,dest,report=lambda *_:None):")
s=change(s,"        inspect_document(doc)\n        for page in doc:","        report('Checking original PDF structure')\n        inspect_document(doc)\n        report('Original structure check passed')\n        for page in doc:\n            report('Rasterization and OCR: page %d of %d' % (page.number+1,doc.page_count))")
s=change(s,"    with f.open(str(dest),filetype='pdf') as final:\n        inspect_document(final)","    report('Checking reconstructed PDF structure and OCR text')\n    with f.open(str(dest),filetype='pdf') as final:\n        inspect_document(final)")
s=change(s,"    root=Path(root); folder=Path(folder); db=root/'definitions'\n    try:","    root=Path(root); folder=Path(folder); db=root/'definitions'\n    def report(msg):\n        try:\n            with (folder/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(msg)+'\\n')\n        except OSError:pass\n    try:")
s=change(s,"        file_check(src); digest=sha256(src)\n        defs=clam_scan(src,db); yara_scan(src,rules)","        report('Checking staged PDF header, end marker and hash')\n        file_check(src); digest=sha256(src)\n        report('ClamAV scanning staged PDF')\n        defs=clam_scan(src,db)\n        report('ClamAV scan completed; starting YARA')\n        yara_scan(src,rules)\n        report('YARA scan completed without policy matches')")
s=change(s,"            text,pages,searchable=reconstruct(src,dest)","            text,pages,searchable=reconstruct(src,dest,report)")
s=change(s,"            second=clam_scan(dest,db); yara_scan(dest,rules)","            report('ClamAV scanning reconstructed PDF')\n            second=clam_scan(dest,db)\n            report('Reconstructed ClamAV scan completed; starting YARA')\n            yara_scan(dest,rules)\n            report('Reconstructed YARA scan completed without policy matches')")
s=change(s,"def invoke(mode,root,folder):","def invoke(mode,root,folder,progress=None):")
s=change(s,"    rc,out=run(cmd,WORKER_TIMEOUT,cwd=folder)","    if progress is None:\n        rc,out=run(cmd,WORKER_TIMEOUT,cwd=folder)\n    else:\n        import threading\n        finished=threading.Event()\n        path=folder/'progress.jsonl'\n        def follow():\n            sent=0\n            while True:\n                try:\n                    if path.is_file() and path.stat().st_size<=65536:\n                        lines=path.read_text(encoding='utf-8').splitlines()\n                        for line in lines[sent:]:\n                            try:msg=json.loads(line)\n                            except ValueError:break\n                            if isinstance(msg,str):progress(msg[:180])\n                            sent+=1\n                except (OSError,UnicodeError):pass\n                if finished.wait(.2):\n                    # Final evidence is checked by the caller; no success is inferred from progress.\n                    break\n        watcher=threading.Thread(target=follow,daemon=True);watcher.start()\n        try:rc,out=run(cmd,WORKER_TIMEOUT,cwd=folder)\n        finally:finished.set();watcher.join(1)")
s=change(s,"def __init__(self,root,threat_action='delete'):","def __init__(self,root,threat_action='delete',progress=None):\n        self.progress=progress or (lambda *_:None)\n        self.worker_progress=progress")
s=change(s,"                db_state(self.root/'definitions')\n                src,digest,size,final=net.download(result.url,folder)","                self.progress('Checking definition freshness and retrieving into quarantine')\n                db_state(self.root/'definitions')\n                src,digest,size,final=net.download(result.url,folder)\n                self.progress('Download completed; checking staged bytes')")
s=change(s,"                r=invoke('inspect',self.root,folder)","                r=invoke('inspect',self.root,folder,self.worker_progress) if self.worker_progress else invoke('inspect',self.root,folder)")
s=change(s,"                dest=folder/'rebuilt.pending';file_check(dest)","                self.progress('Validating worker evidence against exact input and reconstructed bytes')\n                dest=folder/'rebuilt.pending';file_check(dest)")
s=change(s,"            r=invoke('rescan',self.root,folder)","            r=invoke('rescan',self.root,folder,self.worker_progress) if self.worker_progress else invoke('rescan',self.root,folder)")
s=change(s,"    def export(self,digest,directory):","    def export(self,digest,directory,title=None):\n        from desktop_helpers import unique_pdf_path")
s=change(s,"            target=Path(directory)/('PDFResearch_'+digest[:20]+'.pdf')","            target=Path(directory)/('PDFResearch_'+digest[:20]+'.pdf') if title is None else unique_pdf_path(directory,title)")
p.write_text(s,encoding='utf-8')
p=root/'test_security.py';s=p.read_text(encoding='utf-8')
anchor="def rebuild(src,dest):dest.write_bytes(DERIVATIVE);return 'text',1,True"
if s.count(anchor)!=2:raise RuntimeError('Expected two existing mocked reconstruction functions')
s=s.replace(anchor,"def rebuild(src,dest,report=lambda *_:None):dest.write_bytes(DERIVATIVE);return 'text',1,True")
p.write_text(s,encoding='utf-8')
print('v0.4 desktop and security progress overlay applied.')
