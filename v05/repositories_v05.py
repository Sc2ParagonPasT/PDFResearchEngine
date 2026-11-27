"""Repository registry and search scheduler. All network access uses the existing approved-host transport."""
import collections, concurrent.futures as cf, dataclasses, re, sqlite3, time
from contextlib import closing, contextmanager
from urllib.parse import urlencode,urljoin,urlsplit,unquote
from urllib.robotparser import RobotFileParser
from engine import Result,checked_url,safe_title,Links,crawl
from discovery_v03 import Network,discover,PROVIDERS,DEFAULT_PROVIDERS,VERIFIED
LIMITS=(50,100,250,500,1000,2000)
DEFAULT_LIMIT=100
MAX_PER_TASK=40
@dataclasses.dataclass(frozen=True)
class Repository:
    key:str
    name:str
    category:str
    adapter:str
    hosts:tuple=()
    status:str='Available'
GROUPS={'ERIC':'Academic & education','Europe PMC':'Medicine','NASA NTRS':'Science & technology','Library of Congress':'History & archives','Crossref':'Academic & education','arXiv':'Science & technology'}
SOURCES=tuple(Repository(p,p,GROUPS[p],'legacy',status='Available' if p in DEFAULT_PROVIDERS else 'Optional / not fully validated') for p in PROVIDERS)+(
    Repository('zenodo','Zenodo','Independent research','zenodo',('zenodo.org',)),
    Repository('government-attic','Government Attic','Government secrecy & FOIA','attic',('www.governmentattic.org','governmentattic.org')),
)
BY_KEY={s.key:s for s in SOURCES}
CUSTOM=Repository('custom','Approved sites','Custom archives','custom')
@dataclasses.dataclass
class Document(Result):
    authors:str=''
    keywords:str=''
def normalize_limit(v):
    try:v=int(v)
    except (TypeError,ValueError,OverflowError):return DEFAULT_LIMIT
    return v if v in LIMITS else DEFAULT_LIMIT
def words(s):
    return set(re.findall(r'[^\W_]{2,}',str(s).casefold()))-{'the','and','for','with','pdf','pdfs','paper','papers','research','study','studies','article','articles','literature','review','documents','document','empirical','theoretical','framework','systematic'}
def score(q,s):return len(words(q)&words(s))
def candidate(s,net,term,title,url,year='',authors='',keywords=''):
    try:return Document(safe_title(title),checked_url(url,net.hosts),s.name,str(year or '')[:10],term,authors=safe_title(authors) if authors else '',keywords=safe_title(keywords) if keywords else '')
    except (ValueError,TypeError):return None

class MetadataIndex:
    """Metadata only, not document bytes. Cached URLs must pass the live PDF probe again."""
    def __init__(self,path):
        self.path=path
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS documents(source TEXT,url TEXT,title TEXT,year TEXT,authors TEXT,keywords TEXT,query TEXT,checked INTEGER,PRIMARY KEY(source,url))')
            c.execute('CREATE INDEX IF NOT EXISTS recent ON documents(checked)')
            c.execute('CREATE TABLE IF NOT EXISTS source_state(source TEXT PRIMARY KEY,checked INTEGER,reachable INTEGER,detail TEXT)')
    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as c:
            with c:yield c
    def remember(self,s,r):
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?)',(s.key,r.url,r.title,r.year,getattr(r,'authors',''),getattr(r,'keywords',''),r.query,int(time.time())))
            c.execute('DELETE FROM documents WHERE rowid IN (SELECT rowid FROM documents ORDER BY checked DESC,rowid DESC LIMIT -1 OFFSET 50000)')
    def matches(self,s,term):
        q=sorted(words(term))[:8]
        if not q:return []
        sql=' OR '.join('(title LIKE ? OR keywords LIKE ? OR authors LIKE ? OR query LIKE ?)' for _ in q)
        with self.db() as c:rows=c.execute('SELECT url,title,year,authors,keywords,query FROM documents WHERE source=? AND ('+sql+') ORDER BY checked DESC LIMIT 120',[s.key]+['%'+w+'%' for w in q for _ in range(4)]).fetchall()
        rows.sort(key=lambda r:-score(term,' '.join(str(x or '') for x in r[1:])))
        return [Document(t,u,s.name,y or '',term,authors=a or '',keywords=k or '') for u,t,y,a,k,q in rows[:40] if score(term,' '.join(str(x or '') for x in (t,a,k,q)))]
    def state(self,s,n,detail):
        with self.db() as c:c.execute('INSERT OR REPLACE INTO source_state VALUES(?,?,?,?)',(s.key,int(time.time()),n,str(detail)[:300]))
def zenodo(net,s,term,stop):
    data=net.json('https://zenodo.org/api/records?'+urlencode({'q':term,'size':15}))
    out=[]
    for d in data.get('hits',{}).get('hits',[])[:15]:
        if stop.is_set():break
        if not isinstance(d,dict):continue
        m=d.get('metadata') or {};access=d.get('access') or {}
        if m.get('access_right')!='open' and access.get('files')!='public':continue
        authors=', '.join(str(x.get('name','')) for x in (m.get('creators') or [])[:30] if isinstance(x,dict))
        tags=', '.join(str(x) for x in (m.get('keywords') or [])[:30])
        for f in (d.get('files') or [])[:8]:
            if not isinstance(f,dict) or not str(f.get('key','')).lower().endswith('.pdf'):continue
            l=f.get('links') or {}
            r=candidate(s,net,term,m.get('title') or f['key'],l.get('self') or l.get('content'),str(m.get('publication_date',''))[:4],authors,tags)
            if r:out.append(r)
    return out[:40]

class GovernmentAttic:
    def __init__(self):self.records=None;self.robots={}
    def permitted(self,net,u):
        host=urlsplit(u).hostname
        if host not in self.robots:
            p=RobotFileParser()
            try:p.parse(net.bytes('https://'+host+'/robots.txt',256*1024).decode('utf-8','replace').splitlines())
            except Exception as e:
                if str(e)!='HTTP 404':raise ValueError('Cannot establish robots.txt access: '+str(e)) from e
                p.parse([])
            self.robots[host]=p
        return self.robots[host].can_fetch('PDFResearch',u)
    def __call__(self,net,s,term,stop):
        if self.records is None:
            records={};errors=[]
            for u in ('https://www.governmentattic.org/Frame-2.html','https://www.governmentattic.org/docs/'):
                if stop.is_set():return []
                try:
                    if not self.permitted(net,u):raise ValueError('Catalog access disallowed by robots.txt')
                    p=Links();p.feed(net.bytes(u,8*1024*1024).decode('utf-8','replace'))
                    for href,title in p.links[:40000]:
                        try:v=checked_url(urljoin(u,href),net.hosts)
                        except (ValueError,TypeError):continue
                        if not urlsplit(v).path.lower().endswith('.pdf'):continue
                        name=unquote(urlsplit(v).path.rsplit('/',1)[-1])
                        label=safe_title(title)
                        if label in ('Untitled','PDF','Download') or label.lower().endswith('.pdf'):label=name[:-4].replace('_',' ').replace('-',' ')
                        records.setdefault(v,(safe_title(label),name))
                except Exception as e:errors.append(str(e)[:200])
            if not records:raise ValueError('Government Attic catalog unavailable: '+('; '.join(errors) or 'No PDF links'))
            self.records=records
        ranked=sorted(((score(term,t+' '+re.sub(r'([a-z])([A-Z])',r'\1 \2',n)),u,t) for u,(t,n) in self.records.items()),key=lambda x:(-x[0],x[1]))
        out=[]
        for relevance,u,t in ranked:
            if not relevance or stop.is_set() or len(out)>=40:break
            if not self.permitted(net,u):continue
            r=candidate(s,net,term,t,u)
            if r:out.append(r)
        return out

class Session:
    def __init__(self,net,seeds,index):
        self.net=net;self.seeds=seeds;self.index=index;self.adapters={'zenodo':zenodo,'attic':GovernmentAttic()};self.networks={}
    def transport(self,s):
        if not set(s.hosts)<=set(self.net.hosts):raise ValueError('Explicit domain approval required for '+s.name)
        if not s.hosts:return self.net
        if s.key not in self.networks:self.networks[s.key]=Network(s.hosts)
        return self.networks[s.key]
    def discover(self,s,term,stop):
        if stop.is_set():return [],''
        net=self.transport(s);cached=[];error=''
        try:
            if self.index:cached=self.index.matches(s,term)
        except (OSError,sqlite3.Error) as e:error='Metadata cache: '+str(e)
        try:
            if s.adapter=='legacy':fresh=discover(net,s.key,term)
            elif s.adapter=='custom':fresh=crawl(net,self.seeds,term,stop)
            else:fresh=self.adapters[s.adapter](net,s,term,stop)
        except Exception as e:fresh=[];error=(error+'; ' if error else '')+str(e)
        out={}
        for r in fresh+cached:
            try:
                u=checked_url(r.url,net.hosts);out.setdefault(u,dataclasses.replace(r,url=u))
            except (ValueError,TypeError):continue
        return list(out.values())[:40],error
    def verify(self,s,r,stop):
        if stop.is_set():raise ValueError('Cancelled')
        net=self.transport(s)
        # Recheck robots for cached directory records too.
        if s.adapter=='attic' and not self.adapters['attic'].permitted(net,r.url):raise ValueError('Disallowed by robots.txt')
        u,_,_=net.probe(r.url)
        return dataclasses.replace(r,url=checked_url(u,net.hosts),status=VERIFIED)
def interleave(groups):
    queues=[(s,collections.deque(items)) for s,items in groups]
    while queues:
        remaining=[]
        for s,q in queues:
            if q:yield s,q.popleft()
            if q:remaining.append((s,q))
        queues=remaining
def run_search(net,keys,terms,seeds,stop,emit,index=None,limit=DEFAULT_LIMIT):
    limit=normalize_limit(limit);budget=min(8000,limit*4);deadline=time.monotonic()+600
    sources=[BY_KEY[k] for k in dict.fromkeys(keys) if k in BY_KEY]
    if seeds:sources.append(CUSTOM)
    session=Session(net,seeds,index);seen=set();final=set();counts=collections.Counter();errors=collections.Counter();rejected=0
    def halt():return stop.is_set() or time.monotonic()>=deadline or len(final)>=limit or len(seen)>=budget
    def log(v):emit('log',str(v)[:300])
    with cf.ThreadPoolExecutor(max_workers=3) as dp,cf.ThreadPoolExecutor(max_workers=4) as pp:
        for term in terms[:24]:
            if halt():break
            groups=[]
            for offset in range(0,len(sources),3):
                if halt():break
                chunk=sources[offset:offset+3];futures=[dp.submit(session.discover,s,term,stop) for s in chunk]
                for s,f in zip(chunk,futures):
                    try:
                        items,err=f.result()
                        if err:errors[s.key]+=1;log(s.name+': '+err)
                    except Exception as e:items=[];errors[s.key]+=1;log(s.name+': '+str(e))
                    groups.append((s,items))
                emit('progress',f'Checking repositories: {min(offset+3,len(sources))}/{len(sources)} | {len(final)} PDFs found')
            pending=iter(interleave(groups))
            while not halt():
                wave=[]
                while len(wave)<min(4,limit-len(final)) and len(seen)<budget and not stop.is_set():
                    try:s,r=next(pending)
                    except StopIteration:break
                    if r.url in seen:continue
                    seen.add(r.url);wave.append((s,r))
                if not wave:break
                futures=[pp.submit(session.verify,s,r,stop) for s,r in wave]
                for (s,r),f in zip(wave,futures):
                    try:
                        item=f.result()
                        if stop.is_set():continue
                        if index:
                            try:index.remember(s,item)
                            except (OSError,sqlite3.Error) as e:log('Metadata cache: '+str(e))
                        if item.url in final:continue
                        final.add(item.url);counts[s.key]+=1;emit('result',item)
                    except Exception:rejected+=1
                emit('progress',f'{len(final)}/{limit} reachable PDFs | {rejected} excluded | {len(seen)} candidates')
    for s in sources:
        detail=f'{counts[s.key]} results; {errors[s.key]} discovery errors';log(s.name+': '+detail)
        if index:
            try:index.state(s,counts[s.key],detail)
            except (OSError,sqlite3.Error) as e:log('Metadata cache: '+str(e))
    reason=' (stopped)' if stop.is_set() else ' (time limit)' if time.monotonic()>=deadline else ' (result limit)' if len(final)>=limit else ' (candidate limit)' if len(seen)>=budget else ''
    emit('done',f'{len(final)} reachable PDFs; {rejected} excluded; {sum(errors.values())} source errors{reason}. Security inspection still required.')
