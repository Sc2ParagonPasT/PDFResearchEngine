"""Verified discovery layer; no PDF parser or full-file storage during discovery."""
import concurrent.futures as cf
import collections
import dataclasses
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit
import engine as base
from engine import Result, checked_url, HEADER, MAX_PDF

PROVIDERS = ('ERIC', 'Europe PMC', 'NASA NTRS', 'Library of Congress', 'Crossref', 'arXiv')
DEFAULT_PROVIDERS = ('ERIC', 'Europe PMC', 'NASA NTRS')
VERIFIED = 'PDF reachable / unscanned'
MAX_CANDIDATES = 100
MAX_RESULTS = 50

class Network(base.Network):
    def json(self, url):
        # Retry only transient read/connection timeouts, once; preserve all URL/DNS/TLS checks.
        for attempt in range(2):
            try:
                data = super().json(url)
                if not isinstance(data, dict):
                    raise ValueError('Unexpected repository response type')
                if data.get('error'):
                    raise ValueError('Repository API error: '+str(data['error'])[:180])
                return data
            except TimeoutError:
                if attempt: raise
                time.sleep(1)

    def probe(self, url):
        # Use the same full GET as download, but close after reading 1024 bytes.
        # Some servers refuse Range; a successful range request also need not imply GET works.
        c, r, final = self.open(url)
        try:
            if r.status != 200:
                raise ValueError('Full GET required')
            length = r.getheader('Content-Length')
            if length is not None and not 0 < int(length) <= MAX_PDF:
                raise ValueError('File exceeds 50 MB limit or invalid length')
            data = self.read_up_to(r, 1024, time.monotonic()+25)
            if not HEADER.match(data):
                raise ValueError('No PDF signature at beginning of response')
            if length is not None and len(data) < min(int(length), 1024):
                raise ValueError('Truncated response')
            return checked_url(final, self.hosts), r.getheader('Content-Type', ''), ''
        finally:
            r.close(); c.close()


def discover(net, provider, term):
    items = []
    def add(title, url, year=''):
        try:
            url = checked_url(url, net.hosts)
        except (ValueError, TypeError):
            return
        items.append(Result(base.safe_title(title), url, provider, str(year or '')[:10], term))
    if provider == 'ERIC':
        data = net.json('https://api.ies.ed.gov/eric/?'+urlencode({'search':term, 'format':'json','rows':40,'start':0}))
        for d in data.get('response',{}).get('docs',[]):
            flag = d.get('fulltext')
            if flag is not None and str(flag).lower() not in ('t','true','1','yes'):
                continue
            ident = d.get('id','')
            if isinstance(ident,str) and re.fullmatch(r'E[DJ]\d+',ident):
                add(d.get('title'),'https://files.eric.ed.gov/fulltext/'+ident+'.pdf',d.get('publicationdateyear'))
    elif provider == 'Europe PMC':
        data = net.json('https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':'('+term+') AND OPEN_ACCESS:Y','format':'json','pageSize':15,'resultType':'core'}))
        for d in data.get('resultList',{}).get('result',[]):
            for u in d.get('fullTextUrlList',{}).get('fullTextUrl',[]):
                if str(u.get('documentStyle','')).lower()=='pdf' and str(u.get('availabilityCode','')).upper() in ('OA','F'):
                    add(d.get('title'),u.get('url'),d.get('pubYear'))
            # No speculative identifier-to-PDF URL construction.
    elif provider == 'NASA NTRS':
        data = net.json('https://ntrs.nasa.gov/api/citations/search?'+urlencode({'q':term,'downloadsAvailable':'true','page.size':40,'page.from':0}))
        for d in data.get('results',[]):
            for download in d.get('downloads',[]) or []:
                links = download.get('links') or {}
                u = links.get('pdf') if isinstance(links,dict) else None
                if isinstance(u,str):
                    add(d.get('title'),urljoin('https://ntrs.nasa.gov/',u),str(d.get('publicationDate') or '')[:4])
    elif provider == 'Library of Congress':
        data = net.json('https://www.loc.gov/search/?'+urlencode({'fo':'json','q':term,'c':10,'fa':'access-restricted:false'}))
        for d in data.get('results',[]):
            if d.get('access_restricted') is True:
                continue
            for resource in d.get('resources',[]) or []:
                if not isinstance(resource,dict): continue
                u=resource.get('pdf')
                if isinstance(u,str): add(d.get('title'),urljoin('https://www.loc.gov/',u),d.get('date'))
                for group in resource.get('files',[]) or []:
                    for f in group if isinstance(group,list) else [group]:
                        if isinstance(f,dict) and str(f.get('mimetype','')).lower()=='application/pdf' and isinstance(f.get('url'),str):
                            add(d.get('title'),urljoin('https://www.loc.gov/',f['url']),d.get('date'))
    else:
        return base.discover(net,provider,term)
    return items[:40]


def run_search(net, providers, terms, seeds, stop, emit):
    """Only publish verified URLs. Bounded queues, dedupe originals and final redirects."""
    tasks = collections.deque((p,t) for t in terms[:24] for p in providers if p in PROVIDERS)
    if seeds and terms: tasks.appendleft(('Site crawl',terms[0]))
    seen=set(); final_seen=set(); rejected=collections.Counter(); counts=collections.Counter()
    pending=[]; providers_pending={}; probes_pending={}; maxed=False
    def discovery_job(p,t):
        if stop.is_set(): return []
        return base.crawl(net,seeds,t,stop) if p=='Site crawl' else discover(net,p,t)
    def verify_job(item):
        if stop.is_set(): raise ValueError('Cancelled')
        url,_,_=net.probe(item.url)
        return dataclasses.replace(item,url=url,status=VERIFIED)
    with cf.ThreadPoolExecutor(max_workers=3) as discover_pool, cf.ThreadPoolExecutor(max_workers=4) as verify_pool:
        while not stop.is_set():
            if len(seen)>=MAX_CANDIDATES or len(final_seen)>=MAX_RESULTS:
                maxed=True; tasks.clear()
            while tasks and len(providers_pending)<3 and len(pending)<12 and not maxed:
                p,t=tasks.popleft(); providers_pending[discover_pool.submit(discovery_job,p,t)]=(p,t)
            while pending and len(probes_pending)<4 and len(final_seen)<MAX_RESULTS:
                item=pending.pop(0); probes_pending[verify_pool.submit(verify_job,item)]=item
            if not providers_pending and not probes_pending and not pending: break
            if len(final_seen)>=MAX_RESULTS: break
            finished,_=cf.wait(set(providers_pending)|set(probes_pending),return_when=cf.FIRST_COMPLETED,timeout=.2)
            for f in finished:
                if stop.is_set(): break
                if f in providers_pending:
                    p,t=providers_pending.pop(f)
                    try:
                        for item in f.result():
                            if len(seen)>=MAX_CANDIDATES: maxed=True;break
                            if item.url not in seen:
                                seen.add(item.url);pending.append(item)
                    except Exception as e:
                        counts['source errors']+=1;emit('log',f'{p}: {str(e)[:180]}')
                else:
                    item=probes_pending.pop(f)
                    try:
                        item=f.result()
                        if item.url not in final_seen and len(final_seen)<MAX_RESULTS:
                            final_seen.add(item.url);emit('result',item)
                    except Exception as e:
                        m=re.search(r'HTTP (\d{3})',str(e)); reason='HTTP '+m.group(1) if m else type(e).__name__
                        rejected[reason]+=1
            emit('progress',f'{len(final_seen)} reachable PDFs | {sum(rejected.values())} excluded | {len(seen)} candidates discovered')
        for f in list(providers_pending)+list(probes_pending): f.cancel()
    detail=', '.join(f'{k}: {v}' for k,v in rejected.most_common())
    if detail: emit('log','Excluded inaccessible or invalid PDF candidates: '+detail)
    emit('done',f'{len(final_seen)} reachable PDFs; {sum(rejected.values())} excluded; {counts["source errors"]} source errors'+(' (limit reached)' if maxed else '')+(' (stopped)' if stop.is_set() else '')+'. Security inspection still required.')
