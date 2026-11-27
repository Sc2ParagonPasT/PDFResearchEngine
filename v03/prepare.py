"""Apply the v0.3 discovery overlay to the verified v0.2 archive."""
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
overlay = Path(__file__).resolve().parent
for name in ("discovery_v03.py", "test_discovery_v03.py", "live_retrieval.py"):
    shutil.copyfile(overlay / name, root / name)
p = root / "app.py"
s = p.read_text(encoding="utf-8")
changes = [
    ("from engine import *", "from engine import *\nfrom discovery_v03 import Network, PROVIDERS, DEFAULT_PROVIDERS, run_search, VERIFIED"),
    ("value=p in ('ERIC','Europe PMC','Crossref')", "value=p in DEFAULT_PROVIDERS"),
    ("        for p,v in self.providers.items():ttk.Checkbutton(opts,text=p,variable=v).pack(side='left',padx=(0,12))", "        for i,(p,v) in enumerate(self.providers.items()):ttk.Checkbutton(opts,text=p,variable=v).grid(row=i//3,column=i%3,sticky='w',padx=(0,12))"),
    ("ttk.Checkbutton(opts,text='Crawl approved seed pages',variable=self.crawlvar).pack(side='left')", "ttk.Checkbutton(opts,text='Crawl approved seed pages',variable=self.crawlvar).grid(row=2,column=0,columnspan=3,sticky='w')"),
    ("Ready. Discovery results are unverified.", "Ready. Search results have a verified PDF header and accessible URL, but remain unscanned."),
    ("Searching approved sources…", "Searching and verifying approved PDF sources…"),
    ("Check PDF headers", "Recheck PDF access"),
    ("r.status='PDF header confirmed / unscanned'", "r.status=VERIFIED"),
]
for old,new in changes:
    if s.count(old)!=1: raise RuntimeError("Unexpected app source: "+old[:80])
    s=s.replace(old,new)
# Preserve existing library and settings path; only change display version.
s=s.replace("v0.2","v0.3")
p.write_text(s,encoding="utf-8")
print("Applied v0.3 discovery UI overlay; existing library and security settings unchanged.")
