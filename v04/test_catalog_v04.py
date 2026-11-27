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
    def test_catalog_manifest_and_blob_validation(self):
        import base64,hashlib,json
        manifest=bundled_manifest();version,sources=parse_manifest(manifest)
        self.assertEqual(version,1);self.assertEqual(len(sources),len(CATALOG))
        data=json.dumps(manifest).encode();metadata={'path':'catalog/sources.json','encoding':'base64','type':'file','size':len(data),'sha':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),'content':base64.b64encode(data).decode()}
        net=Network(['api.github.com'])
        with patch.object(net,'json',return_value=metadata):self.assertEqual(fetch_manifest(net),manifest)
        with patch.object(net,'json',return_value=dict(metadata,sha='0'*40)):
            with self.assertRaises(ValueError):fetch_manifest(net)
        manifest['sources'][0]['adapter']='arbitrary-code'
        with self.assertRaises(ValueError):parse_manifest(manifest)
    def test_xml_rejects_dtd(self):
        with self.assertRaises(ValueError):xml_root(b'<!DOCTYPE a><a/>')
