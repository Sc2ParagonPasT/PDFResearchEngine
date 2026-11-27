"""Overlay on exact v0.4.1; no security or storage migration."""
import sys,shutil,subprocess
from pathlib import Path
root=Path(sys.argv[1]);here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'v04'/'prepare.py'),str(root)],check=True)
for name in ('repositories_v05.py','desktop_v05.py','test_repositories_v05.py','live_repositories_v05.py'):
    shutil.copyfile(here/name,root/name)
p=root/'app.py';s=p.read_text(encoding='utf-8')
for old,new in [('from desktop_v04 import desktop_class','from desktop_v05 import repository_desktop'),('desktop_class(App)(root).win.mainloop()','repository_desktop(App)(root).win.mainloop()')]:
    assert s.count(old)==1,old
    s=s.replace(old,new)
p.write_text(s.replace('v0.4.1','v0.5'),encoding='utf-8')
p=root/'desktop_v04.py';s=p.read_text(encoding='utf-8').replace('v0.4.1 Experimental','v0.5 Experimental').replace('v0.4.1 • Experimental','v0.5 • Experimental')
a='The app checks candidate PDF links before showing them.'
assert s.count(a)==1
p.write_text(s.replace(a,a+' Choose research repositories to select collections and approve new domains. Set Max results to control the search size.'),encoding='utf-8')
