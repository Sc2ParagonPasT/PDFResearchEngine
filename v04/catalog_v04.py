"""Bundled collection catalog and bounded, declarative discovery.
Entries are research candidates, not endorsements or verified live integrations.
No downloaded catalog can run code. Every result uses the v0.3 URL/PDF gate.
"""
import collections
import concurrent.futures as cf
import dataclasses
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urlencode
from urllib.robotparser import RobotFileParser
from engine import Result, checked_url, Links, safe_title, exact_hosts
from discovery_v03 import VERIFIED

CATALOG_VERSION=1
# id | collection | https seed | category | terms
# Named public collection candidates; paths and live capabilities require testing.
RAW = """
blackvault|The Black Vault|https://www.theblackvault.com/documentarchive/|Independent / UFO|ufo uap foia intelligence military classified
nicap|National Investigations Committee on Aerial Phenomena|https://www.nicap.org/|Independent / UFO|ufo uap sightings reports aerial
cufos|Center for UFO Studies|https://www.cufos.org/|Independent / UFO|ufo uap sightings reports
mufon|Mutual UFO Network|https://mufon.com/|Independent / UFO|ufo sightings uap cases
ufodata|UFO Data Acquisition Project|https://www.ufodata.net/|Independent / UFO|ufo instruments detection uap
uapx|UAPx|https://www.uapexpedition.org/|Independent / UFO|uap ufo scientific instrumentation
nuforc|National UFO Reporting Center|https://nuforc.org/|Independent / UFO|ufo sightings reports
spr|Society for Psychical Research|https://www.spr.ac.uk/|Consciousness / psi|parapsychology psychic consciousness telepathy
psi|Psi Encyclopedia|https://psi-encyclopedia.spr.ac.uk/|Consciousness / psi|psi mediumship telepathy reincarnation
rhine|Rhine Research Center|https://www.rhine.org/|Consciousness / psi|parapsychology psychic precognition
pa|Parapsychological Association|https://www.parapsych.org/|Consciousness / psi|parapsychology psi telepathy experiments
sse|Society for Scientific Exploration|https://www.scientificexploration.org/|Unconventional science|anomalies consciousness physics archaeology
jse|Journal of Scientific Exploration|https://journalofscientificexploration.org/|Unconventional science|anomalies consciousness physics psi
ions|Institute of Noetic Sciences|https://noetic.org/|Consciousness / psi|consciousness meditation psi
ian|International Association for Near-Death Studies|https://iands.org/|Consciousness / psi|near death nde consciousness
essentia|Essentia Foundation|https://www.essentiafoundation.org/|Consciousness / philosophy|idealism metaphysics consciousness
scientificmedical|Scientific and Medical Network|https://scientificandmedical.net/|Consciousness / philosophy|consciousness science philosophy
monroe|Monroe Institute|https://www.monroeinstitute.org/|Consciousness / psi|consciousness meditation altered states
sacred|Internet Sacred Text Archive|https://sacred-texts.com/|Esoteric / religion|religion myth magic esoteric occult
theosophy|Theosophical Society archive|https://www.theosociety.org/|Esoteric / religion|theosophy occult esoteric religion
hermetic|Hermetic Library|https://hermetic.com/|Esoteric / religion|hermetic occult magic alchemy
esoteric|Esoteric Archives|https://www.esotericarchives.com/|Esoteric / religion|grimoires magic alchemy occult
gnosis|Gnosis Archive|https://gnosis.org/|Esoteric / religion|gnostic religion scripture
holybooks|Holy Books|https://holybooks.com/|Esoteric / religion|religion buddhism meditation philosophy
ccel|Christian Classics Ethereal Library|https://www.ccel.org/|Religion / history|christian theology church bible
buddhanet|BuddhaNet|https://www.buddhanet.net/|Religion / philosophy|buddhism meditation dharma
accesstoinsight|Access to Insight|https://www.accesstoinsight.org/|Religion / philosophy|buddhism sutta meditation
suttacentral|SuttaCentral|https://suttacentral.net/|Religion / philosophy|buddhism scripture sutta
bahai|Baháʼí Reference Library|https://www.bahai.org/library/|Religion / philosophy|bahai religion scripture
quran|Quranic Arabic Corpus|https://corpus.quran.com/|Religion / linguistics|quran arabic religion
mises|Mises Institute|https://mises.org/|Economics / think tanks|economics money liberty austrian banking
fee|Foundation for Economic Education|https://fee.org/|Economics / think tanks|economics liberty markets
cato|Cato Institute|https://www.cato.org/|Politics / think tanks|politics liberty economics policy
heritage|Heritage Foundation|https://www.heritage.org/|Politics / think tanks|politics government policy
cepr|Center for Economic and Policy Research|https://cepr.net/|Economics / think tanks|economics labor inequality policy
epi|Economic Policy Institute|https://www.epi.org/|Economics / think tanks|labor economics wages inequality
levy|Levy Economics Institute|https://www.levyinstitute.org/|Economics / think tanks|money banking economics
demos|Demos|https://www.demos.org/|Politics / think tanks|democracy politics inequality
tni|Transnational Institute|https://www.tni.org/|Geopolitics / independent|geopolitics corporate power trade
ips|Institute for Policy Studies|https://ips-dc.org/|Geopolitics / independent|politics peace inequality
brookings|Brookings Institution|https://www.brookings.edu/|Politics / think tanks|government policy economics
rand|RAND|https://www.rand.org/|Military / policy|military strategy security policy
csis|Center for Strategic and International Studies|https://www.csis.org/|Geopolitics / think tanks|geopolitics military china security
carnegie|Carnegie Endowment for International Peace|https://carnegieendowment.org/|Geopolitics / think tanks|foreign policy international security
chatham|Chatham House|https://www.chathamhouse.org/|Geopolitics / think tanks|international relations geopolitics
crisis|International Crisis Group|https://www.crisisgroup.org/|Geopolitics / nonprofit|conflict war peace geopolitics
sipri|Stockholm International Peace Research Institute|https://www.sipri.org/|Military / independent|arms military conflict peace
fas|Federation of American Scientists|https://fas.org/|Military / independent|nuclear intelligence military security
arms|Arms Control Association|https://www.armscontrol.org/|Military / independent|arms nuclear missiles treaties
nti|Nuclear Threat Initiative|https://www.nti.org/|Military / nonprofit|nuclear weapons security
icij|International Consortium of Investigative Journalists|https://www.icij.org/|Investigative journalism|offshore corruption finance investigation
propublica|ProPublica|https://www.propublica.org/|Investigative journalism|investigation corruption accountability
bellingcat|Bellingcat|https://www.bellingcat.com/|Investigative journalism|osint investigation conflict
hrw|Human Rights Watch|https://www.hrw.org/|Nonprofit / reports|human rights conflict detention
amnesty|Amnesty International|https://www.amnesty.org/|Nonprofit / reports|human rights detention repression
transparency|Transparency International|https://www.transparency.org/|Nonprofit / reports|corruption transparency governance
eff|Electronic Frontier Foundation|https://www.eff.org/|Nonprofit / technology|surveillance privacy internet freedom
aclu|American Civil Liberties Union|https://www.aclu.org/|Nonprofit / law|rights privacy surveillance law
epic|Electronic Privacy Information Center|https://epic.org/|Nonprofit / technology|privacy surveillance data
citizenlab|Citizen Lab|https://citizenlab.ca/|Independent / technology|surveillance spyware censorship
privacyinternational|Privacy International|https://privacyinternational.org/|Nonprofit / technology|privacy surveillance data
nsarchive|National Security Archive|https://nsarchive.gwu.edu/|Declassified / independent|intelligence declassified diplomacy military
muckrock|MuckRock|https://www.muckrock.com/|FOIA / independent|foia government records investigation
cia|CIA Reading Room|https://www.cia.gov/readingroom/|Declassified / government|intelligence foia mkultra covert
nara|National Archives|https://www.archives.gov/|Archives / government|archives history records declassified
fbi|FBI Vault|https://vault.fbi.gov/|Declassified / government|fbi records surveillance investigation
dod|Department of Defense historical office|https://history.defense.gov/|Military / government|military history defense
army|Army University Press|https://www.armyupress.army.mil/|Military / government|military strategy doctrine history
naval|Naval History and Heritage Command|https://www.history.navy.mil/|Military / government|navy military history
airforce|Air University Press|https://www.airuniversity.af.edu/AUPress/|Military / government|air force military strategy
govinfo|GovInfo|https://www.govinfo.gov/|Government / records|legislation hearings congressional reports
federalreserve|Federal Reserve research|https://www.federalreserve.gov/|Economics / government|monetary economics banking
bis|Bank for International Settlements|https://www.bis.org/|Economics / international|banking monetary finance
imf|International Monetary Fund|https://www.imf.org/|Economics / international|economics finance debt
worldbank|World Bank Open Knowledge Repository|https://openknowledge.worldbank.org/|Economics / international|development economics poverty
un|United Nations Digital Library|https://digitallibrary.un.org/|International / records|international diplomacy treaties
unesco|UNESCO Digital Library|https://unesdoc.unesco.org/|International / records|education heritage culture
who|WHO Institutional Repository|https://iris.who.int/|Health / international|medicine health public health
marxists|Marxists Internet Archive|https://www.marxists.org/|Political theory / archive|marx socialism communism economics
anarchist|The Anarchist Library|https://theanarchistlibrary.org/|Political theory / archive|anarchism political theory
oll|Online Library of Liberty|https://oll.libertyfund.org/|Philosophy / archive|liberty philosophy political theory
gutenberg|Project Gutenberg|https://www.gutenberg.org/|Books / public domain|books literature history philosophy
pdr|Public Domain Review|https://publicdomainreview.org/|History / independent|history books art archives
hathi|HathiTrust|https://www.hathitrust.org/|Books / archive|books history digitized
biodiversity|Biodiversity Heritage Library|https://www.biodiversitylibrary.org/|History / science|natural history biology
wellcome|Wellcome Collection|https://wellcomecollection.org/|History / medicine|medicine history health
smithsonian|Smithsonian Libraries|https://library.si.edu/|History / science|history science archaeology
worldhistory|World History Encyclopedia|https://www.worldhistory.org/|History / independent|ancient history archaeology
archaeology|Archaeological Institute of America|https://www.archaeological.org/|Archaeology / nonprofit|archaeology ancient history
ancientorigins|Ancient Origins|https://www.ancient-origins.net/|Alternative archaeology|ancient archaeology civilizations
graham|Graham Hancock archive|https://grahamhancock.com/|Alternative archaeology|archaeology ancient civilizations
thunderbolts|Thunderbolts Project|https://www.thunderbolts.info/|Unconventional science|electric universe plasma cosmology
aether|Aetherometry|https://www.aetherometry.com/|Unconventional science|physics aether electricity
openlibrary|Open Library|https://openlibrary.org/|Books / archive|books literature history
internetarchive|Internet Archive|https://archive.org/|Books / broad archive|books archives history independent
zenodo|Zenodo open repository|https://zenodo.org/|Broad research / repositories|research science reports data
osf|Open Science Framework|https://osf.io/|Broad research / repositories|research preprints science
figshare|Figshare|https://figshare.com/|Broad research / repositories|research reports papers
""".strip()

@dataclasses.dataclass(frozen=True)
class Source:
    key:str
    name:str
    seed:str
    category:str
    tags:str
    adapter:str='crawl'
    extra_hosts:tuple=()
    @property
    def hosts(self):return tuple(sorted({urlsplit(self.seed).hostname,*self.extra_hosts}))

EXTRAS={
    'blackvault':('documents.theblackvault.com','theblackvault.com'),
    'nicap':('nicap.org',),
    'cufos':('cufos.org',),
    'spr':('spr.ac.uk',),
    'rhine':('rhine.org',),
    'sse':('scientificexploration.org',),
    'marxists':('marxists.org',),
    'buddhanet':('buddhanet.net',),
    'mises':('cdn.mises.org',),
}
def builtin():
    out=[]
    for line in RAW.splitlines():
        key,name,seed,category,tags=line.split('|')
        adapter='zenodo' if key=='zenodo' else 'crawl'
        s=Source(key,name,seed,category,tags,adapter,EXTRAS.get(key,()))
        checked_url(seed,exact_hosts(s.hosts));out.append(s)
    if len({s.key for s in out})!=len(out):raise ValueError('Duplicate catalog id')
    return tuple(out)
CATALOG=builtin()
BY_KEY={s.key:s for s in CATALOG}
def words(value):return set(re.findall(r'[^\W_]{3,}',str(value).lower()))-{'the','and','for','with','research','papers','paper','study','studies','pdf','document','documents'}
def score(query,value):return len(words(query)&words(value))
def choose_sources(keys,terms,limit=8):
    q=' '.join(terms[:6])
    selected=[s for s in CATALOG if s.key in keys]
    ranked=sorted(selected,key=lambda s:(-score(q,s.tags+' '+s.name),s.key))
    relevant=[s for s in ranked if score(q,s.tags+' '+s.name)>0]
    # Always include an enabled broad-search adapter even for niche topics.
    broad=[s for s in selected if s.adapter=='zenodo']
    return list(dict.fromkeys(broad+relevant+ranked))[:limit]

class Index:
    """Only URL/title/source metadata, not original documents. Cached results are re-probed."""
    def __init__(self,path):
        self.path=Path(path)
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE IF NOT EXISTS links(url TEXT PRIMARY KEY,title TEXT,source TEXT,query TEXT,verified INTEGER)')
            c.execute('CREATE TABLE IF NOT EXISTS source_state(source TEXT PRIMARY KEY,checked INTEGER,reachable INTEGER,downloaded INTEGER,detail TEXT)')
    def remember(self,r,key):
        with sqlite3.connect(self.path,timeout=10) as c:
            c.execute('INSERT OR REPLACE INTO links VALUES (?,?,?,?,?)',(r.url,r.title,key,r.query,int(time.time())))
            c.execute('DELETE FROM links WHERE rowid IN (SELECT rowid FROM links ORDER BY verified DESC LIMIT -1 OFFSET 50000)')
    def matches(self,key,query,limit=6):
        with sqlite3.connect(self.path) as c:
            rows=c.execute('SELECT url,title,query FROM links WHERE source=? ORDER BY verified DESC LIMIT 2000',(key,)).fetchall()
        rows=sorted((r for r in rows if score(query,r[1]+' '+r[0])),key=lambda r:-score(query,r[1]+' '+r[0]))
        return rows[:limit]
    def state(self,key,n,detail,downloaded=0):
        with sqlite3.connect(self.path,timeout=10) as c:
            c.execute('INSERT OR REPLACE INTO source_state VALUES(?,?,?,?,?)',(key,int(time.time()),n,downloaded,detail[:180]))
    def states(self):
        with sqlite3.connect(self.path) as c:
            return {x[0]:x[1:] for x in c.execute('SELECT * FROM source_state')}

def xml_root(data):
    if len(data)>1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or bytes([0]) in data:
        raise ValueError('Untrusted XML metadata')
    return ET.fromstring(data)

def discover_source(net,source,term,stop):
    if stop.is_set():return []
    if not set(source.hosts)<=set(net.hosts):raise ValueError('Collection requires explicit domain approval')
    # Restrict each adapter to its own approved host set, not all user-approved hosts.
    allowed=set(source.hosts)
    def checked(u):return checked_url(u,allowed)
    out={}
    def add(url,title):
        try:
            url=checked(url)
            if score(term,title+' '+url) or source.adapter=='zenodo':
                out[url]=Result(safe_title(title or url),url,source.name,'',term)
        except (ValueError,TypeError):pass
    if source.adapter=='zenodo':
        data=net.json('https://zenodo.org/api/records?'+urlencode({'q':term,'size':8}))
        for d in data.get('hits',{}).get('hits',[]):
            meta=d.get('metadata',{});access=d.get('access',{})
            if meta.get('access_right')!='open' and access.get('files')!='public':continue
            for f in d.get('files',[])[:8]:
                if str(f.get('key','')).lower().endswith('.pdf'):
                    link=f.get('links',{}).get('self') or f.get('links',{}).get('content')
                    if isinstance(link,str):add(link,meta.get('title') or f['key'])
        return list(out.values())[:8]
    robots={}
    def rules(url):
        host=urlsplit(url).hostname
        if host not in robots:
            try:
                body=net.bytes('https://'+host+'/robots.txt',256*1024).decode('utf-8','replace')
                rp=RobotFileParser();rp.parse(body.splitlines());robots[host]=rp
            except Exception as e:
                # A missing robots.txt permits access; explicit refusal or unknown errors do not.
                if str(e)=='HTTP 404':
                    rp=RobotFileParser();rp.parse([]);robots[host]=rp
                else:robots[host]=None
        rp=robots[host]
        return rp if rp and rp.can_fetch('PDFResearch',url) else None
    def candidate(url,title):
        try:
            url=checked(url)
            if rules(url):add(url,title)
        except (ValueError,TypeError):pass
    # Sitemap discovery is bounded and uses only the publisher's advertised maps.
    seed=checked(source.seed);rp=rules(seed)
    if not rp:return []
    maps=list(rp.site_maps() or [])[:2];visited_maps=set()
    while maps and len(visited_maps)<3 and not stop.is_set():
        try:
            u=checked(maps.pop(0))
            if u in visited_maps or not rules(u):continue
            visited_maps.add(u);doc=xml_root(net.bytes(u,1024*1024))
            for node in doc:
                loc=next((x.text for x in node if x.tag.rsplit('}',1)[-1]=='loc'),None)
                if not loc:continue
                if node.tag.rsplit('}',1)[-1]=='sitemap' and len(maps)<3:maps.append(loc)
                elif urlsplit(loc).path.lower().endswith('.pdf'):candidate(loc,urlsplit(loc).path.rsplit('/',1)[-1])
                if len(out)>=8:break
        except Exception:continue
    # Small crawl, source-specific, bounded and robots-aware.
    todo=[seed];visited=set()
    while todo and len(visited)<5 and len(out)<8 and not stop.is_set():
        try:
            u=checked(todo.pop(0))
            if u in visited or not rules(u):continue
            visited.add(u);parser=Links();parser.feed(net.bytes(u,1024*1024).decode('utf-8','replace'))
            links=[]
            for href,title in parser.links[:1000]:
                try:v=checked(urljoin(u,href))
                except (ValueError,TypeError):continue
                if urlsplit(v).path.lower().endswith('.pdf') or re.search(r'\bpdf\b',title or '',re.I):
                    candidate(v,title or urlsplit(v).path.rsplit('/',1)[-1])
                elif v not in visited and score(term,title+' '+v):links.append((score(term,title+' '+v),v))
                if len(out)>=8:break
            todo.extend(v for _,v in sorted(set(links),reverse=True)[:4] if v not in todo)
        except Exception:continue
    return list(out.values())[:8]

def search_catalog(net,keys,terms,index,stop,emit,seen):
    if not terms:return
    sources=choose_sources(keys,terms)
    def work(source):
        # Fresh, source-limited transport preserves existing SSRF/redirect/TLS checks.
        from discovery_v03 import Network
        if not set(source.hosts)<=set(net.hosts):return source,[],'Domain approval missing'
        restricted=Network(source.hosts)
        candidates=[]
        for url,title,_ in index.matches(source.key,terms[0]):
            candidates.append(Result(title,url,source.name,'',terms[0]))
        try:candidates.extend(discover_source(restricted,source,terms[0],stop))
        except Exception as e:return source,[],'Discovery: '+str(e)[:140]
        found=[];used=set()
        for r in candidates:
            if stop.is_set() or len(used)>=10:break
            if r.url in used:continue
            used.add(r.url)
            try:
                final,_,_=restricted.probe(r.url)
                r=dataclasses.replace(r,url=final,status=VERIFIED)
                index.remember(r,source.key);found.append(r)
            except Exception:continue
        return source,found,f'{len(found)} reachable PDFs from {len(used)} candidates'
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(work,s) for s in sources]
        for i,f in enumerate(cf.as_completed(futures),1):
            source,found,detail=f.result()
            index.state(source.key,len(found),detail)
            if not stop.is_set():
                for r in found:
                    if r.url not in seen:seen.add(r.url);emit('result',r)
                emit('progress',f'Additional collections: {i}/{len(sources)} checked; {len(seen)} reachable PDFs total')
                emit('log',source.name+': '+detail)
