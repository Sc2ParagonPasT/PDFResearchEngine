"""Candidate-only live evidence, not a release gate or assertion of live success.
Two independent query attempts per source. Full downloads into temporary quarantine,
never into the user library. Only fixed, explicitly reviewed source host lists.
"""
import concurrent.futures as cf,hashlib,json,platform,tempfile,threading
from pathlib import Path
from adapters_v053 import BY_KEY,discover
from repositories_v05 import Network
from context_v052 import Policy
CASES={
 'internetarchive':('Abraham Lincoln','French Revolution'),
 'documentcloud':('FBI','government surveillance'),
 'figshare':('climate change','reading comprehension'),
 'osf':('social identity','reading comprehension'),
}
def check(key):
    s=BY_KEY[key];net=Network(s.hosts);stop=threading.Event()
    report={'source':s.name,'approved_hosts':list(s.hosts),'queries':[],'downloaded':[],'notes':[],'errors':[]}
    hashes=set();urls=set()
    with tempfile.TemporaryDirectory(prefix='pdfresearch-v053-') as td:
        for term in CASES[key]:
            row={'query':term,'metadata_candidates':0,'relevant':0,'verified':0,'sample':[],'errors':[]}
            try:
                candidates,notes=discover(net,key,term,stop);row['metadata_candidates']=len(candidates);report['notes'].extend(notes)
                matched=[(Policy(term).evaluate(r),r) for r in candidates]
                ranked=sorted(((m,r) for m,r in matched if m is not None),key=lambda x:-x[0].score)
                row['relevant']=len(ranked)
                for match,r in ranked[:8]:
                    try:
                        u,_,_=net.probe(r.url)
                        if u in urls:continue
                        urls.add(u);row['verified']+=1;row['sample'].append({'title':r.title,'url':u,'score':match.score,'reason':match.reason})
                        if len(hashes)<2:
                            p,digest,size,final=net.download(u,Path(td))
                            if not p.is_file() or p.suffix!='.quarantine' or size<=0:raise ValueError('Quarantine invariant failed')
                            if digest not in hashes:
                                hashes.add(digest);report['downloaded'].append({'query':term,'title':r.title,'url':final,'sha256':digest,'bytes':size})
                            p.unlink()
                    except Exception as e:row['errors'].append(str(e)[:240])
            except Exception as e:row['errors'].append(str(e)[:240])
            report['queries'].append(row)
    report['notes']=list(dict.fromkeys(report['notes']))[:100]
    report['passed']=len(hashes)>=2 and all(x['verified']>0 for x in report['queries'])
    return report
if __name__=='__main__':
    with cf.ThreadPoolExecutor(max_workers=2) as pool:reports=list(pool.map(check,CASES))
    out={'platform':platform.platform(),'candidate_sources':len(reports),'passed_sources':[r['source'] for r in reports if r['passed']],'reports':reports,'scope':'Development evidence only; no application registry changes or release. Success requires two distinct complete quarantine downloads and a relevant verified PDF from both query topics.'}
    Path('repository-candidates-v053.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2),flush=True)
    # A successful workflow means the report was collected, not that every adapter passed.
