"""Context-sensitive, bounded metadata ranking over the v0.5.1 transport.
Nothing here parses PDFs, contacts a service, or evaluates a publication's viewpoint.
"""
import dataclasses
import re
from functools import lru_cache
from urllib.parse import unquote,urlsplit
from relevance_v051 import Match,MODES,STOP,CONTEXT,tokens,phrase,stem,clauses,mode_name
from vocabulary_v052 import VOCAB,PROFILES,ALTERNATE,INHERENT

def split(v):return tuple(x.strip() for x in v.split('|') if x.strip())
def norm(v):return tuple(stem(x) for x in tokens(v))
@lru_cache(maxsize=4096)
def normalized_term(v):return norm(v)
def unique(values):return tuple(dict.fromkeys(x for x in values if x))
@dataclasses.dataclass(frozen=True)
class Concept:
    name:str
    direct:tuple
    related:tuple=()
    broad:tuple=()
CONCEPTS=tuple(Concept(n,unique((n,*split(a))),split(b),split(c)) for n,a,b,c in VOCAB)
# Prefer longer aliases when parsing explicit multiword concepts.
ALIASES={}
for c in CONCEPTS:
    for a in c.direct:ALIASES.setdefault(normalized_term(a),c)
MAX_ALIAS=max(map(len,ALIASES))
TRIGGERS={k:{normalized_term(x)[0] for x in split(v[0])} for k,v in PROFILES.items()}
CUES={k:split(v[1]) for k,v in PROFILES.items()}
SOFT=CONTEXT-{'society','social','sociology','societal','community','communities','group','groups','psychology','psychological','history','historical','culture','cultural','politics','political','science','scientific'}
# 'literature' is a stopword in the earlier generic tokenizer; an explicit literary query is context.
IGNORE=STOP-{'literature'}
@dataclasses.dataclass(frozen=True)
class Intent:
    concepts:tuple
    profiles:tuple
    original:str

@lru_cache(maxsize=512)
def intent(query):
    raw=tokens(query);xs=tuple(stem(x) for x in raw);anchors=[];profiles=[];i=0
    while i<len(xs):
        found=None
        for n in range(min(MAX_ALIAS,len(xs)-i),0,-1):
            c=ALIASES.get(xs[i:i+n])
            if c is not None:found=(c,n);break
        if found:
            c,n=found;anchors.append(c);i+=n;continue
        x=raw[i];sx=xs[i];i+=1
        keys=[k for k,triggers in TRIGGERS.items() if sx in triggers]
        if keys:profiles.extend(keys);continue
        if x in IGNORE or x in SOFT or len(x)<2:continue
        anchors.append(Concept(x,(x,)))
    if not anchors:
        # Broad topics remain searchable; do not turn 'society' or 'history' into an empty query.
        anchors=[Concept(x,(x,)) for x in raw if x not in IGNORE and len(x)>1]
        profiles=[]
    return Intent(unique(anchors),unique(profiles),query)

def query_terms(query,mode='Balanced'):
    query=' '.join(str(query or '').split())[:240];mode=mode_name(mode)
    if not query:return []
    parsed=intent(query);terms=[query]
    # Every expansion preserves the remaining concepts and the explicit domain context.
    anchors=parsed.concepts
    if not anchors:return terms
    ctx=[k if k!='social' else 'society' for k in parsed.profiles]
    bases=[a.name for a in anchors]
    terms.append(' '.join((*bases,*ctx)))
    for i,a in enumerate(anchors):
        other=bases[:i]+bases[i+1:]
        direct=[x for x in a.direct if x!=a.name]
        related=list(a.related) if mode!='Focused' else []
        broad=list(a.broad) if mode=='Exploratory' else []
        if mode=='Focused':choices=direct[:6]
        elif mode=='Balanced':choices=[*direct[:3],*related[:7],*direct[3:7]]
        else:choices=[*direct[:4],*related[:8],*broad[:5],*direct[4:9]]
        for synonym in choices:terms.append(' '.join((synonym,*other,*ctx)))
    if mode!='Focused':terms.extend((query+' research',query+' literature review',query+' historical analysis'))
    # Original topic stays first; no broad context-only queries.
    return list(unique(terms))[:{'Focused':5,'Balanced':12,'Exploratory':24}[mode]]

@dataclasses.dataclass(frozen=True)
class Field:
    name:str
    words:tuple
    weight:int
@dataclasses.dataclass(frozen=True)
class Hit:
    field:Field
    term:str
    kind:str
    start:int
    end:int
    value:int
def positions(words,term):
    t=normalized_term(term);n=len(t)
    if not n:return []
    # Whole-token matching, including conservative plural normalization.
    return [(i,i+n) for i in range(len(words)-n+1) if words[i:i+n]==t]
def field_list(r):
    fields=[]
    def add(name,text,weight):
        w=norm(str(text or '')[:8000])
        if w:fields.append(Field(name,w,weight))
    add('title',r.title,26)
    add('keywords',getattr(r,'keywords',''),15)
    name=unquote(urlsplit(r.url).path.rsplit('/',1)[-1]);add('filename',re.sub(r'(?i)\.pdf$','',name),9)
    # Keep nearby concepts in the same sentence/segment. Avoid unrelated terms scattered through abstracts.
    for segment in re.split(r'[.!?;\n]+',str(getattr(r,'description','') or '')[:8000])[:80]:
        add('description',segment,7)
    return fields
def hits(concept,fields):
    found=[]
    for kind,choices,base in (('Direct',concept.direct,56),('Related',concept.related,35),('Exploratory',concept.broad,18)):
        for f in fields:
            for term in choices:
                for a,b in positions(f.words,term):
                    found.append(Hit(f,term,kind,a,b,base+f.weight+(3 if b-a>1 else 0)))
    return sorted(found,key=lambda h:(-h.value,-(h.end-h.start),h.term))
def distance(a,b,c,d):return max(0,c-b,a-d)
def linked(h,cues):
    # Relationship evidence in the same metadata field, close enough to be meaningful.
    return any(distance(h.start,h.end,a,b)<=12 for cue in cues for a,b in positions(h.field.words,cue))
def strong_link(h,profile):
    return linked(h,CUES[profile]) or h.term in INHERENT.get(profile,())
def alternate_domains(fields,profiles):
    title=next((f for f in fields if f.name=='title'),None)
    if title is None:return ()
    return tuple(k for k,terms in ALTERNATE.items() if k not in profiles and any(positions(title.words,x) for x in terms))

@dataclasses.dataclass(frozen=True)
class Policy:
    query:str
    mode:str='Balanced'
    required:tuple=()
    excluded:tuple=()
    def evaluate(self,r):
        parsed=intent(self.query);mode=mode_name(self.mode);fields=field_list(r)
        if not parsed.concepts or not fields:return None
        if any(not any(positions(f.words,t) for f in fields) for t in self.required):return None
        if any(any(positions(f.words,t) for f in fields) for t in self.excluded):return None
        all_hits=[hits(c,fields) for c in parsed.concepts]
        allowed={'Direct'} if mode=='Focused' else {'Direct','Related'} if mode=='Balanced' else {'Direct','Related','Exploratory'}
        usable=[[h for h in hs if h.kind in allowed] for hs in all_hits]
        n=len(usable);missing=sum(not hs for hs in usable)
        if missing and mode!='Exploratory':return None
        if missing>n//2 or missing==n:return None
        # Select an occurrence with linked context rather than rewarding an isolated title keyword.
        selected=[]
        for hs in usable:
            if not hs:continue
            selected.append(max(hs,key=lambda h:(h.value+18*sum(strong_link(h,p) for p in parsed.profiles),h.value,h.end-h.start)))
        supported=[];absent=[]
        for p in parsed.profiles:
            # With multiple concepts, each explicit context must connect to at least one actual topic occurrence.
            linked_hits=[h for hs in usable for h in hs if strong_link(h,p)]
            (supported if linked_hits else absent).append(p)
        if absent and mode!='Exploratory':return None
        # Multiple concepts must share a metadata field (or both occur in title/keywords/filename).
        # Separate abstract sentences alone cannot establish a high-confidence relationship.
        relation=True
        if n>1:
            active=[hs for hs in usable if hs]
            relation=any(all(any(h.field==f for h in hs) for hs in active) for f in fields)
            if not relation:
                relation=all(any(h.field.name in ('title','keywords','filename') for h in hs) for hs in active)
            if not relation and mode=='Focused':return None
        # Do not suppress legitimate interdisciplinary topics. A conflicting domain is only a concern
        # when the original topic explicitly specifies a different contextual profile.
        alternate=alternate_domains(fields,parsed.profiles) if parsed.profiles else ()
        if alternate and 'social' in parsed.profiles:
            title_link=any(h.field.name=='title' and strong_link(h,'social') for hs in usable for h in hs)
            if not title_link and mode!='Exploratory':return None
        score=sum(h.value for h in selected)/n
        if parsed.profiles:score+=16*len(supported)/len(parsed.profiles)-18*len(absent)/len(parsed.profiles)
        if not relation:score-=12
        if alternate:score-=18
        if missing:score-=12*missing/n
        if any(f.name=='title' and positions(f.words,self.query) for f in fields):score+=8
        score=max(1,min(100,round(score)))
        if mode=='Exploratory' and (absent or missing or alternate or any(h.kind=='Exploratory' for h in selected)):
            score=min(score,48)
        if mode=='Focused' and score<50:return None
        if mode=='Balanced' and score<36:return None
        why=[h.kind+': '+h.term+' ('+h.field.name+')' for h in selected]
        if supported:why.append('Context: '+', '.join(supported))
        if absent:why.append('Context missing: '+', '.join(absent))
        if alternate:why.append('Different domain: '+', '.join(alternate))
        if not relation:why.append('Concepts not linked in one field')
        if missing:why.append('Incomplete topic')
        if self.required:why.append('Required terms matched')
        return Match(score,'; '.join(why)[:300])
