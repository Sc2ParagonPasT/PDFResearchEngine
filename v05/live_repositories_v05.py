"""Require two distinct complete public quarantine downloads from each new repository."""
import concurrent.futures as cf,json,tempfile,threading,platform
from pathlib import Path
from repositories_v05 import BY_KEY,Network,run_search,VERIFIED
CASES={'zenodo':'consciousness','government-attic':'FBI'}
def check(key):
    s=BY_KEY[key];net=Network(s.hosts);results=[];messages=[];stop=threading.Event()
    out={'source':s.name,'query':CASES[key],'verified':0,'downloaded':[],'errors':[]}
    def emit(k,v):
        if k=='result':results.append(v)
        elif k in ('log','done'):messages.append(v)
        if len(results)>=8:stop.set()
    try:
        run_search(net,[key],[CASES[key]],[],stop,emit,limit=50)
        out['verified']=len(results);out['messages']=messages
        with tempfile.TemporaryDirectory(prefix='pdfresearch-v05-') as td:
            hashes=set()
            for r in results[:8]:
                try:
                    assert r.status==VERIFIED
                    p,digest,size,final=net.download(r.url,Path(td))
                    if not p.is_file() or p.suffix!='.quarantine' or size<=0:raise ValueError('Quarantine validation failed')
                    if digest not in hashes:out['downloaded'].append({'title':r.title,'url':final,'sha256':digest,'bytes':size});hashes.add(digest)
                    if len(hashes)>=2:break
                except Exception as e:out['errors'].append(str(e)[:200])
    except Exception as e:out['errors'].append(str(e)[:200])
    return out
if __name__=='__main__':
    with cf.ThreadPoolExecutor(max_workers=2) as pool:reports=list(pool.map(check,CASES))
    report={'passed':all(len(r['downloaded'])>=2 for r in reports),'platform':platform.platform(),'reports':reports,'scope':'Temporary quarantine downloads only; no document parsing or release'}
    Path('live-repositories-v05.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
