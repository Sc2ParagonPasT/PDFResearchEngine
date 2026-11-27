import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import security as sec
import test_security as fixtures
from reader_v04 import render_worker, validate_stage, read_page, MAX_RENDER_PIXELS
from engine import Result

class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)
        self.root=Path(self.td.name);self.defs=fixtures.dbs(self.root)
        self.pipe=sec.Pipeline(self.root)
        self.lib=sec.ScreenedLibrary(self.root)
        self.folder=self.root/'staging'/'reader-fixture';self.folder.mkdir()
        self.src=self.folder/'input.quarantine'
        try:import pymupdf
        except ImportError:self.skipTest('PDF renderer missing')
        with pymupdf.open() as doc:
            p=doc.new_page(width=400,height=250);p.insert_text((20,40),'Reader regression fixture');doc.save(str(self.src))
        self.digest=sec.sha256(self.src)
        cache=self.root/'processed';cache.mkdir();self.cached=cache/(self.digest+'.screened');self.cached.write_bytes(self.src.read_bytes())
        self.evidence={'verdict':'passed','input_sha256':self.digest,'output_sha256':self.digest,'definitions':self.defs,'rules_sha256':sec.sha256(sec.RULES),'digest':self.digest,'url':'https://www.cia.gov/fixture.pdf','pages':1,'text':'Reader fixture'}
        self.lib.save(Result('Fixture','https://www.cia.gov/fixture.pdf','test'),self.evidence)
        (self.folder/'result.json').write_text(json.dumps(self.evidence))
    def test_render_screened_page(self):
        with patch('security.require_standard_user'):
            info=render_worker(self.root,self.folder,self.digest,1,2.0)
        self.assertEqual(info['pages'],1);self.assertIn('Reader regression fixture',info['text'])
        self.assertLessEqual(info['width']*info['height'],MAX_RENDER_PIXELS)
        self.assertTrue((self.folder/'reader.png').read_bytes().startswith(b'\x89PNG'))
    def test_tampered_derivative_blocks(self):
        self.cached.write_bytes(b'changed')
        with self.assertRaises(sec.Blocked):validate_stage(self.root,self.folder,self.digest)
    def test_missing_or_changed_rescan_evidence_blocks(self):
        (self.folder/'result.json').unlink()
        with self.assertRaises(sec.Blocked):validate_stage(self.root,self.folder,self.digest)
    def test_blocked_library_row_cannot_render(self):
        self.lib.blocked(self.digest,'test')
        with self.assertRaises(sec.Blocked):validate_stage(self.root,self.folder,self.digest)
        with patch.object(self.pipe,'ensure_ready') as ready:
            with self.assertRaises(sec.Blocked):read_page(self.pipe,self.lib,self.digest,1,1.0)
            ready.assert_not_called()
    def test_outside_stage_rejected(self):
        with self.assertRaises(sec.Blocked):validate_stage(self.root,self.root,self.digest)
