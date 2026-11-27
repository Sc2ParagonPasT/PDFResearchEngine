"""Live, bounded retrieval smoke test. Raw responses are never opened or parsed."""
import concurrent.futures
import json
import tempfile
import threading
from pathlib import Path
from discovery_v03 import Network, run_search, DEFAULT_PROVIDERS, VERIFIED
from engine import DEFAULT_HOSTS

TOPICS = {'ERIC':'reading comprehension', 'NASA NTRS':'Apollo 11',
          'Europe PMC':'malaria vaccine', 'Library of Congress':'civil war maps'}

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
            for item in results[:4]:
                if len(report['downloaded'])>=2: break
                try:
                    assert item.status==VERIFIED
                    file,digest,size,final=net.download(item.url,Path(td))
                    if not file.is_file() or file.suffix!='.quarantine' or size<=0:
                        raise RuntimeError('Download did not produce quarantine file')
                    report['downloaded'].append({'title':item.title,'url':final,'bytes':size,'sha256':digest})
                except Exception as e:
                    report['errors'].append({'url':item.url,'reason':str(e)[:300]})
    except Exception as e:
        report['errors'].append({'reason':str(e)[:300]})
    return report

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        reports=list(pool.map(lambda p:check(p,TOPICS[p]),TOPICS))
    # Do not declare readiness until every default repository produces two full PDFs.
    passed=all(len(r['downloaded'])>=2 for r in reports if r['provider'] in DEFAULT_PROVIDERS)
    output={'passed':passed,'required_default_sources':list(DEFAULT_PROVIDERS),
            'reports':reports,'scope':'Discovery and transport only; no PDFs opened, parsed, or distributed. Raw fixtures removed from temporary storage.'}
    Path('live-retrieval-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2),flush=True)
    raise SystemExit(0 if passed else 1)
