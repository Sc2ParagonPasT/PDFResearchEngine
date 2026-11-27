import sqlite3,tempfile,threading,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from relevance_v051 import *
from repositories_v05 import Document,MetadataIndex,BY_KEY,Network,Session,run_search,VERIFIED
def doc(title,source='Zenodo',url='https://zenodo.org/a.pdf',**kw):return Document(title,url,source,**kw)
class RelevanceTests(unittest.TestCase):
    def test_fairy_tales_context_drift(self):
        for mode in MODES:
            p=Policy('Hatred in Society',mode)
            self.assertIsNone(p.evaluate(doc('Fairy Tales in Modern Society',query='social structure')))
            self.assertIsNone(p.evaluate(doc('Society and culture',url='https://zenodo.org/a.pdf?hatred=1')))
            self.assertIsNotNone(p.evaluate(doc('Collective hatred and society')))
    def test_modes_and_metadata(self):
        a=doc('The psychology of dehumanization');b=doc('Social identity theory')
        self.assertIsNone(Policy('Hatred in Society','Focused').evaluate(a))
        self.assertIsNotNone(Policy('Hatred in Society').evaluate(a))
        self.assertIsNone(Policy('Hatred in Society').evaluate(b))
        self.assertIsNotNone(Policy('Hatred in Society','Exploratory').evaluate(b))
        self.assertIsNotNone(Policy('Hatred in Society').evaluate(doc('Group attitudes',description='An investigation of collective hatred.')))
        self.assertGreater(Policy('Hatred in Society').evaluate(doc('Hatred in society')).score,Policy('Hatred in Society').evaluate(a).score)
    def test_expansion(self):
        terms=query_terms('Hatred in Society','Balanced')
        self.assertIn('prejudice',terms)
        self.assertNotIn('social structure',terms);self.assertNotIn('society',terms)
        self.assertTrue(all('banking' in t.lower() for t in query_terms('CIA banking','Balanced')))
    def test_filters(self):
        p=Policy('hatred','Balanced',clauses('social conflict, history'),clauses('fairy tales, fiction'))
        self.assertIsNotNone(p.evaluate(doc('Hatred and social conflict',description='History of a conflict.')))
        self.assertIsNone(p.evaluate(doc('Hatred and social conflict',description='History of fairy tales.')))
        self.assertIsNone(p.evaluate(doc('Hatred and conflict',description='History of society.')))
        self.assertIsNone(Policy('hate').evaluate(doc('Whatever happens')))
    def test_multiconcept(self):
        self.assertIsNone(Policy('CIA banking').evaluate(doc('CIA history')))
        self.assertIsNotNone(Policy('CIA banking').evaluate(doc('Central Intelligence Agency banking')))
        self.assertIsNotNone(Policy('society').evaluate(doc('Society and culture')))
        self.assertIsNotNone(Policy('FBI').evaluate(doc('Federal Bureau of Investigation records')))
    def test_duplicate_grouping(self):
        a=doc('Hatred and social conflict',authors='Jane Doe',year='2020',identifier='10.1234/test',relevance=90)
        b=doc('Hatred and social conflict','arXiv','https://arxiv.org/a.pdf',identifier='https://doi.org/10.1234/test',relevance=70)
        c=doc('Hatred and social conflict','ERIC','https://files.eric.ed.gov/other.pdf',relevance=65)
        rows=ordered([b,c,a]);self.assertEqual(len(rows),2);self.assertEqual(rows[0].alternatives,(('arXiv','https://arxiv.org/a.pdf'),))
    def test_cache_migration(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'old.db'
            with closing(sqlite3.connect(p)) as c:
                with c:
                    c.execute('CREATE TABLE documents(source TEXT,url TEXT,title TEXT,year TEXT,authors TEXT,keywords TEXT,query TEXT,checked INTEGER,PRIMARY KEY(source,url))')
                    c.execute("INSERT INTO documents VALUES('zenodo','https://zenodo.org/a.pdf','Hatred in Society','2020','','','society',1)")
            i=MetadataIndex(p);self.assertEqual(len(i.matches(BY_KEY['zenodo'],'hatred')),1)
            i.remember(BY_KEY['zenodo'],doc('Group relations',url='https://zenodo.org/b.pdf',description='Social hostility in society'))
            self.assertEqual(i.matches(BY_KEY['zenodo'],'hostility')[0].description,'Social hostility in society')
            # Explicit unlink also detects leaked production cache handles on Windows.
            p.unlink()
            self.assertFalse(p.exists())
    def test_filter_before_probe_and_rank(self):
        events=[];records=[doc('Fairy tales in society',url='https://zenodo.org/fairy.pdf'),doc('Dehumanization',url='https://zenodo.org/weak.pdf'),doc('Hatred in society',url='https://zenodo.org/strong.pdf')]
        with patch.object(Session,'discover',return_value=(records,'')),patch.object(Network,'probe',side_effect=lambda u:(u,'','')) as probe:
            run_search(Network(['zenodo.org']),['zenodo'],['society'],[],threading.Event(),lambda k,v:events.append((k,v)),policy=Policy('Hatred in society'))
        self.assertEqual(probe.call_count,2);self.assertEqual([v.title for k,v in events if k=='result'],['Hatred in society','Dehumanization'])
        self.assertTrue(all(v.status==VERIFIED for k,v in events if k=='result'))
    def test_discovery_query_not_evidence(self):
        self.assertIsNone(Policy('hatred').evaluate(doc('Fairy tales',query='hatred and society')))
