"""Relevance overlay over the validated v0.5 baseline; security unchanged."""
import sys,shutil,subprocess
from pathlib import Path
root=Path(sys.argv[1]);here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here.parent/'v05'/'prepare.py'),str(root)],check=True)
for name in ('relevance_v051.py','test_relevance_v051.py','repositories_v05.py','desktop_v05.py','live_repositories_v05.py'):
    shutil.copyfile(here/name,root/name)
def change(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)
for name in ('app.py','desktop_v04.py'):
    p=root/name;s=p.read_text(encoding='utf-8');s=s.replace('v0.5','v0.5.1')
    if name=='desktop_v04.py':s=change(s,'Set Max results to control the search size.','Set Max results to control the search size. Choose Focused, Balanced or Exploratory relevance. Optional Require and Exclude fields take comma-separated words or phrases. Scores are metadata matches, not probabilities.')
    p.write_text(s,encoding='utf-8')
# Add optional metadata fields, preserving original positional Result arguments.
p=root/'engine.py';s=p.read_text(encoding='utf-8')
s=change(s,"status:str='Candidate (unverified)';digest:str=''","status:str='Candidate (unverified)';digest:str='';authors:str='';keywords:str='';description:str='';identifier:str=''")
s=change(s,"def add(title,url,year=''):\n        try:url=checked_url(url,net.hosts)","def add(title,url,year='',authors='',keywords='',description='',identifier=''):\n        try:url=checked_url(url,net.hosts)")
s=change(s,"items.append(Result(safe_title(title),url,provider,str(year or '')[:10],term))","items.append(Result(safe_title(title),url,provider,str(year or '')[:10],term,authors=safe_title(authors) if authors else '',keywords=safe_title(keywords) if keywords else '',description=' '.join(re.sub(r'<[^>]+>',' ',str(description or '')[:16000]).split())[:8000],identifier=str(identifier or '')[:300]))")
s=change(s,"add(e.findtext('a:title',default='Untitled',namespaces=ns),u,e.findtext('a:published',default='',namespaces=ns)[:4])","add(e.findtext('a:title',default='Untitled',namespaces=ns),u,e.findtext('a:published',default='',namespaces=ns)[:4],', '.join(a.findtext('a:name',default='',namespaces=ns) for a in e.findall('a:author',ns)[:30]),'',e.findtext('a:summary',default='',namespaces=ns),e.findtext('{http://arxiv.org/schemas/atom}doi',default=''))")
p.write_text(s,encoding='utf-8')
p=root/'discovery_v03.py';s=p.read_text(encoding='utf-8')
s=change(s,"def add(title, url, year=''):","def add(title, url, year='', authors='', keywords='', description='', identifier=''):")
s=change(s,"items.append(Result(base.safe_title(title), url, provider, str(year or '')[:10], term))","items.append(Result(base.safe_title(title), url, provider, str(year or '')[:10], term,authors=base.safe_title(authors) if authors else '',keywords=base.safe_title(keywords) if keywords else '',description=' '.join(re.sub(r'<[^>]+>',' ',str(description or '')[:16000]).split())[:8000],identifier=str(identifier or '')[:300]))")
s=change(s,"add(d.get('title'),'https://files.eric.ed.gov/fulltext/'+ident+'.pdf',d.get('publicationdateyear'))","add(d.get('title'),'https://files.eric.ed.gov/fulltext/'+ident+'.pdf',d.get('publicationdateyear'),d.get('author'),d.get('descriptor'),d.get('description'))")
s=change(s,"add(d.get('title'),u,d.get('pubYear'))","add(d.get('title'),u,d.get('pubYear'),d.get('authorString'),'',d.get('abstractText'),d.get('doi'))")
s=change(s,"add(d.get('title'),u.get('url'),d.get('pubYear'))","add(d.get('title'),u.get('url'),d.get('pubYear'),d.get('authorString'),'',d.get('abstractText'),d.get('doi'))")
s=change(s,"add(d.get('title'),urljoin('https://ntrs.nasa.gov/',u),str(d.get('publicationDate') or d.get('distributionDate') or '')[:4])","add(d.get('title'),urljoin('https://ntrs.nasa.gov/',u),str(d.get('publicationDate') or d.get('distributionDate') or '')[:4],d.get('authorAffiliations'),d.get('keywords'),d.get('abstract'))")
p.write_text(s,encoding='utf-8')
