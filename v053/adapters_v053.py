"""v0.5.3 candidate adapters. Not registered in the desktop until live validation.
All transport uses the v0.5.2 exact-host HTTPS Network. No auth, automatic
host approval, external search engines, file parsing, or access-control bypass.
"""
import re
from urllib.parse import quote,urlencode,urlsplit,urljoin
from engine import checked_url,MAX_PDF
from repositories_v05 import Repository,candidate

SOURCES=(
    Repository('internetarchive','Internet Archive','Books & broad archives','ia',('archive.org',),'Candidate / not yet live validated'),
    Repository('documentcloud','DocumentCloud','Primary documents & journalism','dc',('api.www.documentcloud.org','assets.documentcloud.org','s3.documentcloud.org','www.documentcloud.org'),'Candidate / not yet live validated'),
    Repository('figshare','Figshare','Independent research','figshare',('api.datacite.org','api.figshare.com','ndownloader.figshare.com','figshare.com'),'Candidate / not yet live validated'),
    Repository('osf','Open Science Framework','Independent research','osf',('api.osf.io','osf.io','files.osf.io'),'Candidate / not yet live validated'),
)
BY_KEY={s.key:s for s in SOURCES}

def as_dict(v):return v if isinstance(v,dict) else {}
def as_list(v):return v if isinstance(v,list) else []
def text(v):
    if isinstance(v,list):return ', '.join(text(x) for x in v[:30])
    if isinstance(v,dict):return str(v.get('name') or v.get('title') or v.get('description') or v.get('value') or '')
    return str(v or '')
def yes(v):return v is True or str(v).lower() in ('true','yes','1')
def size_ok(v):
    if v is None or v=='':return True  # existing probe and full download enforce the limit.
    try:return 0<int(v)<=MAX_PDF
    except (ValueError,TypeError,OverflowError):return False
def quoted(q):
    # Treat user input as text, not an injected query expression.
    return '"'+str(q)[:240].replace('\\','\\\\').replace('"','\\"')+'"'
def host_note(url,net,notes):
    try:
        p=urlsplit(url)
        if p.scheme=='https' and p.hostname and p.hostname not in net.hosts:
            notes.append('Unapproved advertised file host: '+p.hostname)
    except (ValueError,TypeError,AttributeError):pass
def add(out,s,net,term,title,url,year='',authors='',keywords='',description='',identifier='',notes=None):
    if not isinstance(url,str):return
    item=candidate(s,net,term,title,url,year,text(authors),text(keywords),text(description),identifier)
    if item:out.append(item)
    elif notes is not None:host_note(url,net,notes)
def public_record(m):
    if any(yes(m.get(x)) for x in ('access-restricted-item','is_embargoed','is_confidential','private','withdrawn','is_withdrawn')):return False
    if m.get('is_public') is False or m.get('is_published') is False:return False
    if m.get('date_withdrawn'):return False
    return True

def internetarchive(net,s,term,stop,notes):
    q='(title:'+quoted(term)+' OR description:'+quoted(term)+' OR subject:'+quoted(term)+') AND mediatype:texts AND format:PDF AND NOT access-restricted-item:true AND NOT collection:inlibrary AND NOT collection:printdisabled'
    response=net.json('https://archive.org/advancedsearch.php?'+urlencode({'q':q,'fl[]':['identifier','title'],'rows':12,'page':1,'output':'json'},doseq=True))
    out=[]
    for d in as_list(as_dict(response.get('response')).get('docs'))[:12]:
        if stop.is_set():break
        ident=as_dict(d).get('identifier')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',ident) or ident in ('.','..'):continue
        try:record=net.json('https://archive.org/metadata/'+quote(ident,safe=''))
        except (OSError,ValueError) as e:notes.append('Archive metadata: '+str(e)[:160]);continue
        m=as_dict(record.get('metadata'))
        if not public_record(m) or m.get('mediatype')!='texts':continue
        if set(as_list(m.get('collection')) or [m.get('collection')])&{'inlibrary','printdisabled','restricted'}:continue
        # Record explicitly advertised storage hosts, but never contact or approve them.
        for k in ('d1','d2','server'):
            h=record.get(k)
            if isinstance(h,str) and re.fullmatch(r'[A-Za-z0-9.-]{1,253}',h) and h not in net.hosts:
                notes.append('Archive advertises unapproved file server: '+h)
        files=[]
        for f in as_list(record.get('files')):
            f=as_dict(f);name=f.get('name')
            if not isinstance(name,str) or not name.lower().endswith('.pdf') or name.startswith('/') or any(x in ('','.','..') for x in name.split('/')):continue
            if yes(f.get('private')) or not size_ok(f.get('size')):continue
            if str(f.get('format','')).lower() not in ('pdf','text pdf','image container pdf','additional pdf'):continue
            files.append(f)
        # Prefer original PDF where present; do not download all derivatives of one item.
        for f in sorted(files,key=lambda x:x.get('source')!='original')[:1]:
            url='https://archive.org/download/'+quote(ident,safe='')+'/'+quote(f['name'],safe='/')
            add(out,s,net,term,m.get('title') or ident,url,m.get('year') or m.get('date'),m.get('creator'),m.get('subject'),m.get('description'),notes=notes)
    return out[:40]

def documentcloud(net,s,term,stop,notes):
    data=net.json('https://api.www.documentcloud.org/api/documents/?'+urlencode({'q':term,'page_size':25}))
    out=[]
    for d in as_list(data.get('results'))[:25]:
        if stop.is_set():break
        d=as_dict(d)
        if not public_record(d):continue
        access=d.get('access')
        # An unauthenticated public search may omit the access field. Unknown explicit
        # access levels are not treated as public until the API schema is verified.
        if access is not None and str(access).lower()!='public':
            notes.append('DocumentCloud explicit access value not yet supported: '+str(access)[:50]);continue
        u=d.get('pdf_url') or d.get('pdfUrl')
        asset=d.get('asset_url');slug=d.get('slug')
        # DocumentCloud exposes an asset base and a slug in its document metadata.
        # Limit construction to the repository's advertised HTTPS asset path.
        if not isinstance(u,str) and isinstance(asset,str):
            if urlsplit(asset).path.lower().endswith('.pdf'):u=asset
            elif isinstance(slug,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,250}',slug) and asset.endswith('/'):
                u=urljoin(asset,slug+'.pdf')
        if not isinstance(u,str):
            notes.append('DocumentCloud record lacks recognized PDF asset metadata; keys: '+','.join(sorted(d))[:220]);continue
        add(out,s,net,term,d.get('title'),u,str(d.get('created_at') or '')[:4],d.get('author'),d.get('tags'),d.get('description'),notes=notes)
    return out[:40]

def figshare(net,s,term,stop,notes):
    # DataCite provides a read-only GET search for Figshare-issued public DOIs.
    # Resolve only DOI IDs matching the documented Figshare article/version pattern.
    q='prefix:10.6084 AND '+quoted(term)
    data=net.json('https://api.datacite.org/dois?'+urlencode({'query':q,'page[size]':20}))
    out=[];seen=set()
    for d in as_list(data.get('data'))[:20]:
        if stop.is_set():break
        a=as_dict(as_dict(d).get('attributes'));doi=str(a.get('doi') or '')
        match=re.fullmatch(r'10\.6084/m9\.figshare\.(\d{1,15})(?:\.v(\d{1,5}))?',doi,re.I)
        if not match or match[1] in seen:continue
        seen.add(match[1])
        if a.get('state') not in (None,'findable'):continue
        path='https://api.figshare.com/v2/articles/'+match[1]+('/versions/'+match[2] if match[2] else '')
        try:m=net.json(path)
        except (ValueError,OSError) as e:notes.append('Figshare article metadata: '+str(e)[:160]);continue
        if not public_record(m):continue
        authors=[as_dict(x).get('full_name') or as_dict(x).get('name') for x in as_list(m.get('authors'))[:30]]
        for f in as_list(m.get('files'))[:10]:
            f=as_dict(f)
            if not str(f.get('name','')).lower().endswith('.pdf') or yes(f.get('is_link_only')) or yes(f.get('private')) or not size_ok(f.get('size')):continue
            u=f.get('downloadUrl') or f.get('download_url')
            add(out,s,net,term,m.get('title'),u,str(m.get('published_date') or '')[:4],authors,m.get('tags'),m.get('description'),m.get('doi') or doi,notes)
    return out[:40]

def osf(net,s,term,stop,notes):
    # The public JSON:API preprint collection and primary-file relationship are
    # sufficient; no project crawls, authentication, or inferred file paths.
    data=net.json('https://api.osf.io/v2/preprints/?'+urlencode({'filter[title]':term,'page[size]':20}))
    out=[]
    for d in as_list(data.get('data'))[:20]:
        if stop.is_set():break
        d=as_dict(d);a=as_dict(d.get('attributes'))
        if not public_record(a):continue
        rel=as_dict(as_dict(d.get('relationships')).get('primary_file'))
        related=as_dict(as_dict(rel.get('links')).get('related')).get('href')
        if not isinstance(related,str):
            notes.append('OSF record lacks primary-file relationship');continue
        try:
            # Metadata requests may only target the dedicated API origin.
            checked_url(related,('api.osf.io',))
            f=as_dict(net.json(related).get('data'))
        except (ValueError,OSError) as e:notes.append('OSF primary file: '+str(e)[:160]);continue
        attrs=as_dict(f.get('attributes'))
        if not public_record(attrs) or not size_ok(attrs.get('size')):continue
        if not str(attrs.get('name','')).lower().endswith('.pdf') and str(attrs.get('content_type','')).lower()!='application/pdf':continue
        u=as_dict(f.get('links')).get('download')
        if isinstance(u,dict):u=u.get('href')
        add(out,s,net,term,a.get('title'),u,str(a.get('date_published') or '')[:4],'',a.get('tags'),a.get('description'),a.get('doi') or '',notes)
    return out[:40]

ADAPTERS={'ia':internetarchive,'dc':documentcloud,'figshare':figshare,'osf':osf}
def discover(net,key,term,stop):
    s=BY_KEY[key]
    if not set(s.hosts)<=set(net.hosts):raise ValueError('Explicit domain approval required for '+s.name)
    if stop.is_set():return [],[]
    notes=[]
    out=ADAPTERS[s.adapter](net,s,term,stop,notes)
    return list({r.url:r for r in out}.values())[:40],list(dict.fromkeys(notes))[:50]
