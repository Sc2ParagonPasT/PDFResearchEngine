import io, threading, unittest
from unittest.mock import Mock, patch
from discovery_v03 import *

class Response(io.BytesIO):
    status=200
    def __init__(self, data, headers=None): super().__init__(data); self.headers=headers or {}
    def getheader(self,key,default=None): return self.headers.get(key,default)

class Tests(unittest.TestCase):
    def test_probe_full_get(self):
        net=Network(['www.cia.gov']);u='https://www.cia.gov/a.pdf'
        r=Response(b'%PDF-1.7\nhello');c=Mock()
        with patch.object(net,'open',return_value=(c,r,u)) as op:
            self.assertEqual(net.probe(u)[0],u);op.assert_called_once_with(u)
        self.assertTrue(r.closed);c.close.assert_called_once()
    def test_probe_rejects_html_large_truncated_and_partial(self):
        net=Network(['www.cia.gov']);u='https://www.cia.gov/a.pdf'
        for data,headers,status in [(b'<html>PDF</html>',{},200),(b'%PDF-1.7\n',{'Content-Length':str(MAX_PDF+1)},200),(b'%PDF-1.7\n',{'Content-Length':'500'},200),(b'%PDF-1.7\n',{},206)]:
            r=Response(data,headers);r.status=status
            with patch.object(net,'open',return_value=(Mock(),r,u)),self.assertRaises(ValueError): net.probe(u)
            self.assertTrue(r.closed)
    def test_ERIC_filters_nonfulltext(self):
        net=Network(base.DEFAULT_HOSTS)
        with patch.object(net,'json',return_value={'response':{'docs':[{'id':'ED123','title':'Good','fulltext':'T'},{'id':'EJ456','title':'Bad','fulltext':'F'}]}}) as get:
            self.assertEqual([x.title for x in discover(net,'ERIC','school')],['Good']);self.assertEqual(base.urlsplit(get.call_args.args[0]).query, 'search=school&format=json&rows=40&start=0')
    def test_repository_api_error_not_silently_empty(self):
        net=Network(base.DEFAULT_HOSTS)
        with patch.object(base.Network,'json',return_value={'error':'unsupported filter'}):
            with self.assertRaisesRegex(ValueError,'Repository API error'): net.json('https://api.ies.ed.gov/eric/')
    def test_metadata_timeout_retries_once(self):
        net=Network(base.DEFAULT_HOSTS)
        with patch.object(base.Network,'json',side_effect=[TimeoutError('timed out'),{'response':{'docs':[]}}]) as get, patch('discovery_v03.time.sleep'):
            self.assertEqual(net.json('https://api.ies.ed.gov/eric/'),{'response':{'docs':[]}});self.assertEqual(get.call_count,2)
        with patch.object(base.Network,'json',side_effect=TimeoutError('timed out')) as get, patch('discovery_v03.time.sleep'):
            with self.assertRaises(TimeoutError): net.json('https://api.ies.ed.gov/eric/')
            self.assertEqual(get.call_count,2)
    def test_official_oa_pdf_only_and_approval(self):
        net=Network([*base.DEFAULT_HOSTS,*OA_HOSTS])
        xml=b'<OA><records><record><link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/a.pdf"/><link format="tgz" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/a.tgz"/><link format="pdf" href="https://unapproved.example/a.pdf"/></record></records></OA>'
        with patch.object(net,'bytes',return_value=xml) as fetch:
            self.assertEqual(oa_pdf_links(net,'PMC123'),['https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/a.pdf'])
            fetch.assert_called_once()
        restricted=Network(['www.ebi.ac.uk'])
        with patch.object(restricted,'bytes') as fetch:
            self.assertEqual(oa_pdf_links(restricted,'PMC123'),[]);fetch.assert_not_called()
        with patch.object(net,'bytes',return_value=b'<!DOCTYPE a><a/>'):
            with self.assertRaises(ValueError): oa_pdf_links(net,'PMC123')
    def test_nasa_paginates_past_metadata_only(self):
        net=Network(base.DEFAULT_HOSTS)
        first={'results':[{'id':i,'title':'No PDF','downloads':[]} for i in range(40)]}
        next_page={'results':[{'id':40,'title':'Report','downloads':[{'links':{'pdf':'/api/citations/40/downloads/a.pdf'}}]}]}
        with patch.object(net,'json',side_effect=[first,next_page]) as get:
            self.assertEqual([x.title for x in discover(net,'NASA NTRS','apollo')],['Report'])
            self.assertIn('page.from=40',get.call_args_list[1].args[0])
    def test_pmc_no_guessed_links(self):
        net=Network([h for h in base.DEFAULT_HOSTS if h not in OA_HOSTS])
        with patch.object(net,'json',return_value={'resultList':{'result':[{'pmcid':'PMC123','title':'No PDF'},{'title':'Good','fullTextUrlList':{'fullTextUrl':[{'documentStyle':'pdf','availabilityCode':'OA','url':'https://europepmc.org/pdf'}]}}]}}):
            self.assertEqual([x.title for x in discover(net,'Europe PMC','health')],['Good'])
    def test_nasa_only_explicit_approved_pdf_links(self):
        net=Network(base.DEFAULT_HOSTS)
        with patch.object(net,'json',return_value={'results':[{'title':'Report','downloads':[{'links':{'pdf':'/api/citations/1/downloads/a.pdf'}},{'links':{'pdf':'https://unapproved.example/a.pdf'}}]},{'title':'No PDF','id':2}]}) as get:
            self.assertEqual([x.url for x in discover(net,'NASA NTRS','apollo')],['https://ntrs.nasa.gov/api/citations/1/downloads/a.pdf'])
            self.assertIn('q=apollo&page.size=40&page.from=0',get.call_args.args[0])
    def test_loc_only_explicit_approved_pdf_links(self):
        net=Network(base.DEFAULT_HOSTS)
        with patch.object(net,'json',return_value={'results':[{'title':'Report','resources':[{'pdf':'/a.pdf'},{'files':[[{'mimetype':'application/pdf','url':'https://unapproved.example/a.pdf'},{'mimetype':'text/html','url':'/b.pdf'}]]}]},{'title':'Private','access_restricted':True,'resources':[{'pdf':'/c.pdf'}]}]}):
            self.assertEqual([x.url for x in discover(net,'Library of Congress','history')],['https://www.loc.gov/a.pdf'])
    def test_search_excludes_failures_dedupes_final(self):
        net=Network(base.DEFAULT_HOSTS);events=[]; urls=['https://www.cia.gov/'+x for x in ('404','403','html','good','duplicate')]
        items=[Result(x,x,'test') for x in urls]
        def probe(url):
            for tag in ('404','403'):
                if url.endswith(tag): raise ValueError('HTTP '+tag)
            if url.endswith('html'): raise ValueError('No PDF signature')
            return urls[3],'application/pdf',''
        with patch('discovery_v03.discover',return_value=items),patch.object(net,'probe',side_effect=probe) as p:
            run_search(net,['ERIC'],['a','b'],[],threading.Event(),lambda k,v:events.append((k,v)))
        results=[v for k,v in events if k=='result'];self.assertEqual(len(results),1);self.assertEqual(results[0].status,VERIFIED);self.assertEqual(p.call_count,5)
        self.assertTrue(any(k=='log' and 'HTTP 403' in v and 'HTTP 404' in v for k,v in events))
    def test_cancelled_search(self):
        stop=threading.Event();stop.set();events=[]
        with patch('discovery_v03.discover') as d:
            run_search(Network(base.DEFAULT_HOSTS),['ERIC'],['x'],[],stop,lambda k,v:events.append((k,v)))
            d.assert_not_called()
        self.assertTrue(any(k=='done' and 'stopped' in v for k,v in events))
