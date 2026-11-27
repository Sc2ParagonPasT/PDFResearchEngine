"""Live validation of representative independent collection candidates; no raw PDF parsing."""
import concurrent.futures as cf
import json, tempfile, threading
from pathlib import Path
from catalog_v04 import BY_KEY, discover_source
from discovery_v03 import Network
CASES={'nicap':'UFO','blackvault':'UFO','jse':'consciousness','mises':'economics','marxists':'economics','buddhanet':'buddhism','zenodo':'consciousness'}
def run(case):
    key,term=case;s=BY_KEY[key];net=Network(s.hosts)
    report={'source':s.name,'key':key,'query':term,'candidates':0,'verified':0,'downloaded':[],'errors':[]}
    try:
        results=discover_source(net,s,term,threading.Event());report['candidates']=len(results)
        with tempfile.TemporaryDirectory() as td:
            hashes=set()
            for r in results:
                try:
                    u,_,_=net.probe(r.url);report['verified']+=1
                    file,digest,size,final=net.download(u,Path(td))
                    if not file.is_file() or file.suffix!='.quarantine':raise ValueError('Missing quarantine file')
                    if digest not in hashes:report['downloaded'].append({'title':r.title,'url':final,'bytes':size,'sha256':digest});hashes.add(digest)
                    if len(hashes)>=2:break
                except Exception as e:report['errors'].append(str(e)[:200])
    except Exception as e:report['errors'].append(str(e)[:200])
    return report
if __name__=='__main__':
    with cf.ThreadPoolExecutor(max_workers=3) as pool:reports=list(pool.map(run,CASES.items()))
    independent=[r for r in reports if r['key']!='zenodo' and len(r['downloaded'])>=2]
    output={'passed':bool(independent),'reports':reports,'scope':'Actual temporary quarantine retrieval only; no document rendering or release.'}
    Path('live-catalog-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2),flush=True)
    raise SystemExit(0 if independent else 1)
