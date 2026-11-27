import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from catalog_v04 import *
from discovery_v03 import Network

class CatalogTests(unittest.TestCase):
    def test_unique_catalog_and_subject_selection(self):
        self.assertGreaterEqual(len(CATALOG),75)
        self.assertEqual(len(CATALOG),len(BY_KEY))
        selected=choose_sources(set(BY_KEY),['UFO intelligence documents'])
        self.assertTrue(any(x.key in ('blackvault','nicap','cufos') for x in selected))
        self.assertLessEqual(len(selected),8)
    def test_unapproved_source_never_contacts_network(self):
        source=BY_KEY['nicap'];net=Network(['arxiv.org'])
        with patch.object(net,'bytes') as get:
            with self.assertRaises(ValueError):discover_source(net,source,'UFO',threading.Event())
            get.assert_not_called()
    def test_sitemap_and_crawl_check_domain_and_robots(self):
        source=Source('test','Test','https://example.org/','History','history')
        net=Network(source.hosts)
        body=b'<a href="/history.pdf">History report</a><a href="https://bad.example/history.pdf">History</a><a href="/private/history.pdf">History</a>'
        def response(url,*_):
            if url.endswith('robots.txt'):return b'User-agent: *\nDisallow: /private/\n'
            return body
        with patch.object(net,'bytes',side_effect=response):
            self.assertEqual([r.url for r in discover_source(net,source,'history',threading.Event())],['https://example.org/history.pdf'])
    def test_index_metadata_only(self):
        with tempfile.TemporaryDirectory() as td:
            idx=Index(Path(td)/'index.db');idx.remember(Result('History report','https://example.org/history.pdf','Example','','history'),'test')
            self.assertEqual(idx.matches('test','history')[0][0],'https://example.org/history.pdf')
            self.assertEqual(idx.matches('test','math'),[])
    def test_xml_rejects_dtd(self):
        with self.assertRaises(ValueError):xml_root(b'<!DOCTYPE a><a/>')
