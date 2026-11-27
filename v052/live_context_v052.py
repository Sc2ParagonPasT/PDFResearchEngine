"""Reproducible fixture benchmark and public metadata sample, no raw document parsing."""
import concurrent.futures as cf,json,threading,time
from pathlib import Path
from engine import DEFAULT_HOSTS
from repositories_v05 import Network,Session,BY_KEY,Document
from relevance_v051 import Policy as PreviousPolicy
from context_v052 import Policy,CONCEPTS
from benchmark_v052 import CASES,LIVE_TOPICS
def result(p,r):
    m=p.evaluate(r)
    return None if m is None else {'score':m.score,'why':m.reason}
def fixtures():
    rows=[]
    for q,a,b,c in CASES:
        for label,t in (('direct',a),('related',b),('off_topic',c)):
            r=Document(t,'https://zenodo.org/example.pdf','Fixture')
            rows.append({'query':q,'label':label,'title':t,'v051':result(PreviousPolicy(q),r),'v052':result(Policy(q),r)})
    def totals(k):
        good=[r for r in rows if r['label']!='off_topic'];bad=[r for r in rows if r['label']=='off_topic']
        return {'relevant_retained':sum(r[k] is not None for r in good),'relevant_total':len(good),'off_topic_accepted':sum(r[k] is not None for r in bad),'off_topic_total':len(bad)}
    return {'topics':len(CASES),'vocabulary_concepts':len(CONCEPTS),'v051':totals('v051'),'v052':totals('v052'),'cases':rows,'scope':'Hand-labelled synthetic fixtures; not an independent corpus or real-world accuracy estimate.'}
def sample_source(pair):
    key,topics=pair;key='zenodo' if key=='Zenodo' else key
    s=BY_KEY[key];net=Network(s.hosts or DEFAULT_HOSTS);session=Session(net,[],None);rows=[]
    for q in topics:
        try:
            items,err=session.discover(s,q,threading.Event())
            old=[];new=[]
            for r in items:
                a=result(PreviousPolicy(q),r);b=result(Policy(q),r)
                if a:old.append({'title':r.title,**a})
                if b:new.append({'title':r.title,**b})
            new.sort(key=lambda x:-x['score']);old.sort(key=lambda x:-x['score'])
            rows.append({'source':s.name,'query':q,'candidates':len(items),'v051_accepted':len(old),'v052_accepted':len(new),'v051_examples':old[:3],'v052_examples':new[:3],'error':err})
        except Exception as e:
            rows.append({'source':s.name,'query':q,'candidates':0,'error':str(e)[:240]})
        time.sleep(.3)
    return rows
if __name__=='__main__':
    out=fixtures()
    with cf.ThreadPoolExecutor(max_workers=3) as pool:sample=[r for rows in pool.map(sample_source,LIVE_TOPICS.items()) for r in rows]
    report={'fixture_benchmark':out,'live_metadata':{'attempted':len(sample),'nonempty':sum(bool(x['candidates']) for x in sample),'rows':sample,'scope':'Live candidate metadata only, no PDF probes or human relevance labels. Accepted counts are not quality measurements.'}}
    Path('context-benchmark-v052.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    assert out['topics']>=20 and len(sample)>=20
