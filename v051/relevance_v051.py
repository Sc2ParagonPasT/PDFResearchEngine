"""Local, explainable metadata relevance. No document parsing or remote AI."""
import dataclasses,re,unicodedata
from urllib.parse import urlsplit,unquote
from engine import TERM_GROUPS
MODES=('Focused','Balanced','Exploratory')
STOP=set('a an the of in on at to from for by with and or as is are was were be been it its that this these those into about between through across among pdf pdfs paper papers article articles study studies research review literature empirical theoretical systematic framework document documents'.split())
CONTEXT=set('society social sociology societal psychology psychological history historical culture cultural politics political science scientific modern contemporary global world international national human people community communities institutions institutional group groups system systems'.split())
CONCEPTS=(
 ('hatred hate hateful hating hostility hostile animosity antagonism',('collective hatred','social hostility','intergroup hostility','outgroup hostility','social antagonism','hate speech','hate crime'),('prejudice','dehumanization','scapegoating','intolerance','intergroup conflict','affective polarization','collective resentment','moral exclusion','social exclusion'),('social identity theory','intergroup threat','collective aggression','social dominance theory','sociology of emotions')),
 ('ufo ufos uap uaps',('unidentified flying object','unidentified aerial phenomena','unidentified anomalous phenomena','flying saucer'),('aerial anomaly','unexplained aerial sightings','project blue book'),('anomalous radar sightings',)),
 ('foia',('freedom of information act',),('government transparency','declassified records','public records disclosure'),('government secrecy',)),
 ('telepathy telepathic',('extrasensory perception','thought transference'),('parapsychology','anomalous cognition','remote viewing'),('psychical research',)),
 ('consciousness conscious awareness',('conscious experience','subjective experience','states of consciousness'),('phenomenology','mind body problem','altered states'),('philosophy of mind',)),
 ('propaganda',('mass persuasion','information warfare','psychological operations'),('media framing','public opinion formation','political communication'),('social influence','behavioral influence')),
 ('mkultra',('mk ultra','project mkultra'),('cia mind control','behavioral experimentation','project artichoke'),('human experimentation',)),
 ('poverty',('economic deprivation','material hardship','relative deprivation'),('economic inequality','social exclusion'),('social stratification',)),
 ('surveillance',('mass surveillance','electronic surveillance','government surveillance'),('signals intelligence','privacy monitoring'),('civil liberties',)),
 ('fbi',('federal bureau of investigation',),(),()),
 ('cia',('central intelligence agency',),(),()),
)
def tokens(v):
    v=unicodedata.normalize('NFKC',str(v or ''))
    return tuple(re.findall(r'[^\W_]+',re.sub(r'([a-z])([A-Z])',r'\1 \2',v).casefold()))
def phrase(v):return ' '.join(tokens(v))
def meaningful(v):return tuple(dict.fromkeys(x for x in tokens(v) if x not in STOP and len(x)>1))
def stem(x):
    if len(x)>5 and x.endswith('ies'):return x[:-3]+'y'
    if len(x)>4 and x.endswith('s') and not x.endswith(('ss','us','is','ness')):return x[:-1]
    return x
def matches(v,t):
    xs=tokens(v);ts=tokens(t)
    if not ts:return False
    if len(ts)==1:return stem(ts[0]) in {stem(x) for x in xs}
    return (' '+' '.join(ts)+' ') in (' '+' '.join(xs)+' ')
def clauses(v):return tuple(dict.fromkeys(phrase(x) for x in re.split(r'[,;\n]',str(v or '')[:1200]) if phrase(x)))[:20]
def mode_name(v):return v if v in MODES else 'Balanced'
def core(q):
    words=meaningful(q);return tuple(x for x in words if x not in CONTEXT) or words
def concept(a):
    for names,direct,related,broad in CONCEPTS:
        if a in names.split():return tuple(dict.fromkeys([a,*names.split(),*direct])),related,broad
    return (a,),(),()
def query_terms(q,mode='Balanced'):
    q=' '.join(str(q or '').split())[:240];mode=mode_name(mode)
    if not q:return []
    a=core(q);out=[q,' '.join(meaningful(q))]
    if len(a)==1:
        direct,related,broad=concept(a[0])
        # Direct and conceptual terms both receive search slots; context-only terms never do.
        out.extend(x for x in direct if ' ' in x) if mode=='Focused' else out.extend([*direct[-4:],*related,*direct])
        if mode=='Exploratory':out.extend(broad)
        if len(direct)==1 and mode!='Focused':
            for pattern,terms in TERM_GROUPS.items():
                if re.fullmatch('(?:'+pattern+')',a[0],re.I):out.extend(a[0]+' '+t for t in terms)
    elif a:
        for x in a:
            for syn in concept(x)[0][:5]:
                if syn!=x:out.append(' '.join(syn if t==x else t for t in meaningful(q)))
    if mode!='Focused':out.extend((q+' literature review',q+' historical research'))
    return list(dict.fromkeys(x for x in out if x.strip()))[:{'Focused':5,'Balanced':12,'Exploratory':24}[mode]]
@dataclasses.dataclass(frozen=True)
class Match:
    score:int
    reason:str
@dataclasses.dataclass(frozen=True)
class Policy:
    query:str
    mode:str='Balanced'
    required:tuple=()
    excluded:tuple=()
    def evaluate(self,r):
        title=str(r.title or '')
        name=re.sub(r'(?i)\.pdf$','',unquote(urlsplit(r.url).path.rsplit('/',1)[-1]))
        meta=' '.join(str(getattr(r,k,'') or '') for k in ('keywords','description'))
        fields=(title,meta,name)
        if any(not any(matches(f,x) for f in fields) for x in self.required):return None
        if any(any(matches(f,x) for f in fields) for x in self.excluded):return None
        anchors=core(self.query);mode=mode_name(self.mode)
        if not anchors:return None
        direct=[];related=[];broad=[];missing=[];title_hits=0
        for a in anchors:
            aliases,assoc,weak=concept(a)
            hit=next((x for x in aliases if matches(title,x)),None)
            if hit:title_hits+=1;direct.append(hit);continue
            hit=next((x for x in aliases if matches(meta,x) or matches(name,x)),None)
            if hit:direct.append(hit);continue
            hit=next((x for x in assoc if any(matches(f,x) for f in fields)),None)
            if hit:related.append(hit);continue
            hit=next((x for x in weak if any(matches(f,x) for f in fields)),None)
            if hit:broad.append(hit);continue
            missing.append(a)
        if mode=='Focused' and len(direct)!=len(anchors):return None
        if mode=='Balanced' and (missing or broad or not (direct or related)):return None
        if mode=='Exploratory' and (not (direct or related or broad) or len(missing)>len(anchors)//2):return None
        n=len(anchors);score=round((68*len(direct)+48*len(related)+25*len(broad)+18*title_hits)/n)
        if matches(title,self.query):score+=10
        if any(matches(title+' '+meta,x) for x in set(meaningful(self.query))-set(anchors)):score+=4
        reason='; '.join(label+': '+', '.join(dict.fromkeys(items)) for label,items in [('Direct',direct),('Related',related),('Exploratory',broad),('Missing',missing)] if items)
        return Match(min(100,score),reason[:300])
def identity(r):
    doi=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',str(getattr(r,'identifier','')).strip().lower())
    if re.fullmatch(r'10\.\d{4,9}/[^\s]+',doi):return ('doi',doi)
    title=phrase(r.title);author=phrase(getattr(r,'authors',''));year=str(r.year or '')
    if len(title.split())>=4 and author and re.fullmatch(r'\d{4}',year):return ('bibliographic',title,author,year)
    return None
def ordered(items):
    groups={};out=[]
    for r in sorted(items,key=lambda r:(-r.relevance,phrase(r.title),r.url)):
        key=identity(r)
        if key and key in groups and groups[key].source!=r.source:
            first=groups[key];first.alternatives=tuple(dict.fromkeys((*first.alternatives,(r.source,r.url))))
        else:
            if key:groups.setdefault(key,r)
            out.append(r)
    return out
