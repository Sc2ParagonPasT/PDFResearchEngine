"""Live, bounded retrieval smoke test. Raw responses are never opened or parsed."""
import concurrent.futures
import json
import platform
import tempfile
import threading
from pathlib import Path
from discovery_v03 import Network, run_search, DEFAULT_PROVIDERS, VERIFIED
from engine import DEFAULT_HOSTS

TOPICS = {'ERIC':'reading comprehension', 'NASA NTRS':'Apollo 11',
          'Europe PMC':'malaria vaccine', 'Library of Congress':'civil war history', 'arXiv':'information theory'}

def check(provider, term):
    net=Network(DEFAULT_HOSTS)
    results=[]; messages=[]
    def emit(kind,value):
        if kind=='result': results.append(value)
        elif kind in ('log','done'): messages.append(value)
    report={'provider':provider,'term':term,'verified':0,'downloaded':[],'errors':[]}
    try:
        run_search(net,[provider],[term],[],threading.Event(),emit)
        report['verified']=len(results)
        report['messages']=messages
        with tempfile.TemporaryDirectory(prefix='pdfresearch-live-') as td:
            seen_hashes=set()
            for item in results[:6]:
                if len(report['downloaded'])>=2: break
                try:
                    assert item.status==VERIFIED
                    file,digest,size,final=net.download(item.url,Path(td))
                    if not file.is_file() or file.suffix!='.quarantine' or size<=0:
                        raise RuntimeError('Download did not produce quarantine file')
                    if digest in seen_hashes: continue
                    seen_hashes.add(digest)
                    report['downloaded'].append({'title':item.title,'url':final,'bytes':size,'sha256':digest})
                except Exception as e:
                    report['errors'].append({'url':item.url,'reason':str(e)[:300]})
    except Exception as e:
        report['errors'].append({'reason':str(e)[:300]})
    return report


def inspect_metadata():
    """Record bounded public API metadata, not document bytes, to diagnose discovery."""
    from urllib.parse import urlencode
    import discovery_v03 as discovery
    queries = [
        ('ERIC baseline','https://api.ies.ed.gov/eric/?'+urlencode({'search':'reading comprehension','format':'json','rows':3,'start':0})),
        ('ERIC expanded','https://api.ies.ed.gov/eric/?'+urlencode({'search':'reading comprehension','format':'json','rows':40,'start':0})),
        ('NASA second page','https://ntrs.nasa.gov/api/citations/search?'+urlencode({'q':'Apollo 11','page.size':40,'page.from':40})),
        ('NASA fourth page','https://ntrs.nasa.gov/api/citations/search?'+urlencode({'q':'Apollo 11','page.size':40,'page.from':120})),
        ('NASA q','https://ntrs.nasa.gov/api/citations/search?'+urlencode({'q':'Apollo 11','page.size':3})),
        ('Europe PMC','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':'malaria vaccine AND OPEN_ACCESS:Y','format':'json','pageSize':3,'resultType':'core'})),
        ('Library of Congress','https://www.loc.gov/search/?'+urlencode({'fo':'json','q':'civil war history','c':3,'fa':'access-restricted:false|online-format:pdf'})),
    ]
    def examine(entry):
        label,url=entry
        net=Network(DEFAULT_HOSTS)
        out={'label':label,'url':url}
        try:
            data=net.json(url)
            if not isinstance(data,dict):
                out['root_type']=type(data).__name__;return out
            out['root_keys']=list(data)[:40]
            response=data.get('response',{})
            rl=data.get('resultList',{})
            out['counts']={k:data[k] for k in ('hitCount','total','totalResults') if k in data and isinstance(data[k],(int,str))}
            if isinstance(response,dict):
                out['response_keys']=list(response)
                out['numFound']=response.get('numFound')
            if isinstance(rl,dict):out['resultList_keys']=list(rl)
            for k in ('stats','pagination'):
                if k in data:out[k]=str(data[k])[:500]
            records=data.get('results') or (response.get('docs',[]) if isinstance(response,dict) else []) or (rl.get('result',[]) if isinstance(rl,dict) else [])
            out['records']=len(records) if isinstance(records,list) else type(records).__name__
            out['samples']=[]
            if isinstance(records,list):
                out['records_with_downloads']=sum(bool(x.get('downloads')) for x in records if isinstance(x,dict))
            for item in (records[:3]+[x for x in records[3:] if isinstance(x,dict) and x.get('downloads')][:2]) if isinstance(records,list) else []:
                if not isinstance(item,dict):continue
                sample={'keys':list(item)[:60]}
                for key in ('id','title','fulltext','pmcid','downloads','downloadsAvailable','fullTextUrlList','resources','access_restricted','stiType','distribution'):
                    if key in item:sample[key]=str(item[key])[:700]
                out['samples'].append(sample)
            if label.startswith('NASA') and records and isinstance(records,list) and isinstance(records[0],dict):
                ident=records[0].get('id')
                if isinstance(ident,int) or isinstance(ident,str) and ident.isdigit():
                    try:
                        detail=net.json('https://ntrs.nasa.gov/api/citations/'+str(ident))
                        out['citation_detail']={'keys':list(detail)[:60],'downloads':str(detail.get('downloads'))[:1200]} if isinstance(detail,dict) else type(detail).__name__
                    except Exception as e:out['citation_detail_error']=str(e)[:300]
        except Exception as e:out['error']=type(e).__name__+': '+str(e)[:300]
        return out
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(examine,queries))

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        reports=list(pool.map(lambda p:check(p,TOPICS[p]),TOPICS))
    # Do not declare readiness until every default repository produces two full PDFs.
    by_provider={r['provider']:r for r in reports}
    passed=all(p in by_provider and len(by_provider[p]['downloaded'])>=2 for p in DEFAULT_PROVIDERS)
    output={'passed':passed,'platform':platform.platform(),'required_default_sources':list(DEFAULT_PROVIDERS),
            'optional_sources':{r['provider']:('passed' if len(r['downloaded'])>=2 else 'not validated') for r in reports if r['provider'] not in DEFAULT_PROVIDERS},
            'reports':reports,'scope':'Discovery and transport only; no PDFs opened, parsed, or distributed. Raw fixtures removed from temporary storage.'}
    if not passed or any(len(r['downloaded'])<2 for r in reports):
        output['metadata_diagnostics']=inspect_metadata()
    Path('live-retrieval-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2),flush=True)
    raise SystemExit(0 if passed else 1)
