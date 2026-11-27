import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from repositories_v05 import *
class RepositoryTests(unittest.TestCase):
    def test_registry_and_limits(self):
        self.assertEqual(len(SOURCES),len(BY_KEY));self.assertTrue(set(DEFAULT_PROVIDERS)<=set(BY_KEY))
        self.assertEqual(normalize_limit(2000),2000);self.assertEqual(normalize_limit(99999),100)
    def test_unapproved_never_contacts_network(self):
        s=Session(Network(['arxiv.org']),[],None)
        with patch('repositories_v05.Network') as factory:
            with self.assertRaises(ValueError):s.discover(BY_KEY['zenodo'],'psi',threading.Event())
            factory.assert_not_called()
    def test_zenodo_explicit_open_pdfs_only(self):
        net=Network(['zenodo.org'])
        data={'hits':{'hits':[{'metadata':{'title':'Psi study','access_right':'open','creators':[{'name':'A Person'}]},'files':[{'key':'a.pdf','links':{'self':'https://zenodo.org/a.pdf'}},{'key':'b.pdf','links':{'self':'https://evil.example/b.pdf'}},{'key':'a.zip','links':{'self':'https://zenodo.org/a.zip'}}]},{'metadata':{'access_right':'restricted'},'files':[{'key':'c.pdf','links':{'self':'https://zenodo.org/c.pdf'}}]}]}}
        with patch.object(net,'json',return_value=data):r=zenodo(net,BY_KEY['zenodo'],'psi',threading.Event())
        self.assertEqual(len(r),1);self.assertEqual(r[0].authors,'A Person')
    def test_attic_robots_ranking_and_fetch_once(self):
        s=BY_KEY['government-attic'];net=Network(s.hosts);a=GovernmentAttic()
        def response(u,*_):
            if u.endswith('robots.txt'):return b'User-agent: *\nDisallow: /private/\n'
            return b'<a href="/docs/FBI_files.pdf">FBI files</a><a href="/docs/CIA_history.pdf">CIA history</a><a href="/private/FBI.pdf">FBI restricted</a><a href="https://evil.example/FBI.pdf">FBI bad</a>'
        with patch.object(net,'bytes',side_effect=response) as get:
            r=a(net,s,'FBI',threading.Event());n=get.call_count;r2=a(net,s,'CIA',threading.Event());self.assertEqual(get.call_count,n)
        self.assertEqual(len(r),1);self.assertTrue(r[0].url.endswith('/FBI_files.pdf'))
        self.assertEqual(len(r2),1);self.assertTrue(r2[0].url.endswith('/CIA_history.pdf'))
    def test_attic_error_reported(self):
        s=BY_KEY['government-attic'];net=Network(s.hosts)
        with patch.object(net,'bytes',side_effect=ValueError('HTTP 403')):
            with self.assertRaisesRegex(ValueError,'catalog unavailable'):GovernmentAttic()(net,s,'FBI',threading.Event())
    def test_persistent_metadata_reprobed(self):
        s=BY_KEY['zenodo'];net=Network(s.hosts)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'cache.db';i=MetadataIndex(p)
            i.remember(s,Document('Psi experiment','https://zenodo.org/a.pdf','Zenodo',authors='A Person',keywords='telepathy'))
            i=MetadataIndex(p);self.assertEqual(i.matches(s,'telepathy')[0].authors,'A Person')
            events=[]
            with patch('repositories_v05.zenodo',return_value=[]),patch.object(Network,'probe',side_effect=ValueError('HTTP 404')) as probe:
                run_search(net,['zenodo'],['telepathy'],[],threading.Event(),lambda k,v:events.append((k,v)),i)
            probe.assert_called();self.assertFalse(any(k=='result' for k,v in events))
    def test_fair_search_limits_and_deduplication(self):
        net=Network(['arxiv.org','files.eric.ed.gov']);events=[]
        def source(session,s,t,stop):
            h='arxiv.org' if s.key=='arXiv' else 'files.eric.ed.gov'
            return [Result(str(i),f'https://{h}/{i}.pdf',s.name) for i in range(40)],''
        def verify(session,s,r,stop):return dataclasses.replace(r,status=VERIFIED)
        with patch.object(Session,'discover',source),patch.object(Session,'verify',verify):
            run_search(net,['ERIC','arXiv'],['topic','topic'],[],threading.Event(),lambda k,v:events.append((k,v)),limit=50)
        r=[v for k,v in events if k=='result'];self.assertEqual(len(r),50);self.assertEqual(len({x.url for x in r}),50)
        self.assertEqual(collections.Counter(x.source for x in r),{'ERIC':25,'arXiv':25})
    def test_errors_isolated(self):
        events=[]
        def source(session,s,t,stop):
            if s.key=='ERIC':raise ValueError('API unavailable')
            return [Result('paper','https://arxiv.org/a.pdf',s.name)],''
        with patch.object(Session,'discover',source),patch.object(Network,'probe',return_value=('https://arxiv.org/a.pdf','','')):
            run_search(Network(['arxiv.org']),['ERIC','arXiv'],['topic'],[],threading.Event(),lambda k,v:events.append((k,v)))
        self.assertTrue(any(k=='result' for k,v in events));self.assertTrue(any(k=='log' and 'API unavailable' in v for k,v in events))
    def test_cancel_prevents_network(self):
        stop=threading.Event();stop.set()
        with patch.object(Session,'discover') as d:
            run_search(Network(['zenodo.org']),['zenodo'],['psi'],[],stop,lambda *_:None);d.assert_not_called()
