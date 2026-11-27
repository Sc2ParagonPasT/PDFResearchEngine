"""Context update on top of v0.5.1. Prior source trees and security remain intact."""
import shutil,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'v051'/'prepare.py'),str(root)],check=True)
for name in ('context_v052.py','vocabulary_v052.py','benchmark_v052.py','test_context_v052.py','live_context_v052.py','desktop_v05.py','live_repositories_v05.py'):
    shutil.copyfile(here/name,root/name)
for name in ('app.py','desktop_v04.py'):
    p=root/name;s=p.read_text(encoding='utf-8').replace('v0.5.1','v0.5.2')
    if name=='desktop_v04.py':
        a='Scores are metadata matches, not probabilities.'
        assert s.count(a)==1
        s=s.replace(a,a+' Contextual matching uses nearby concepts and reviewed topic relationships, with broader matches kept in Exploratory mode.')
    p.write_text(s,encoding='utf-8')
