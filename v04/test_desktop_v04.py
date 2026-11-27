import tempfile, unittest, threading
from pathlib import Path
from unittest.mock import patch
from desktop_helpers import safe_pdf_name, unique_pdf_path, export_folder, load_preferences, save_preferences
import security as s
import test_security as fixtures

class DesktopTests(unittest.TestCase):
    def test_windows_filename(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(safe_pdf_name('A: B? / C.pdf',td),'A B C.pdf')
            self.assertEqual(safe_pdf_name('CON.txt',td),'_CON.txt.pdf')
            self.assertEqual(safe_pdf_name('...',td),'Research document.pdf')
            self.assertLessEqual(len(safe_pdf_name('x'*1000,td)),180)
    def test_collision_and_preferences(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'Title.pdf').write_bytes(b'old')
            self.assertEqual(unique_pdf_path(p,'Title').name,'Title (2).pdf')
            prefs=p/'ui.json';save_preferences(prefs,{'text_size':18,'last_folder':td})
            self.assertEqual(load_preferences(prefs)['text_size'],18)
            self.assertEqual(export_folder(td),p)
            with patch('desktop_helpers.documents_folder',return_value=p):
                self.assertEqual(export_folder(str(p/'missing')),p)
    def test_named_export_preserves_existing_file_and_rescans(self):
        # Use the existing controlled security fixture, not a mock export function.
        fixture=fixtures.PipelineTests();fixture.setUp()
        try:
            evidence=fixture.accept();dest=fixture.root/'export';dest.mkdir()
            (dest/'Title.pdf').write_bytes(b'old')
            with patch('security.invoke',side_effect=fixture.mock_pass) as w:
                path=fixture.pipe.export(evidence['output_sha256'],dest,title='Title')
            self.assertEqual(path.name,'Title (2).pdf')
            self.assertEqual(path.read_bytes(),fixtures.DERIVATIVE)
            self.assertEqual((dest/'Title.pdf').read_bytes(),b'old')
            self.assertIn('rescan',[c.args[0] for c in w.call_args_list])
        finally:fixture.doCleanups()
    def test_monitor_does_not_release_failed_scan(self):
        fixture=fixtures.PipelineTests();fixture.setUp()
        try:
            events=[];pipe=s.Pipeline(fixture.root,progress=events.append)
            with patch('security.invoke',return_value={'verdict':'unavailable','reason':'scanner failed'}):
                result=pipe.process(fixture.net,fixture.r)
            self.assertEqual(result['verdict'],'unavailable')
            self.assertFalse((fixture.root/'processed').exists())
            self.assertTrue(any('quarantine' in msg for msg in events))
        finally:fixture.doCleanups()

    def test_plain_language_preserves_distinct_security_stages(self):
        from desktop_v04 import plain_stage
        self.assertEqual(plain_stage('ClamAV scanning staged PDF'),'Virus scanning')
        self.assertEqual(plain_stage('ClamAV scanning reconstructed PDF'),'Final virus scan')
        self.assertEqual(plain_stage('Rasterization and OCR: page 2 of 5'),'Rebuilding document and making text searchable: page 2 of 5')
        self.assertEqual(plain_stage('Checking original PDF structure'),'Checking document safety')
        self.assertEqual(plain_stage('Unrecognized scanner error'),'Unrecognized scanner error')
    def test_font_default_bounds_and_wheel(self):
        from desktop_v04 import font_size, wheel_steps
        from types import SimpleNamespace
        self.assertEqual(font_size(None),14)
        self.assertEqual(font_size(18),18)
        self.assertEqual(font_size(99),24)
        self.assertEqual(font_size(0),10)
        self.assertEqual(font_size('nan'),14)
        self.assertEqual(wheel_steps(SimpleNamespace(delta=120)),1)
        self.assertEqual(wheel_steps(SimpleNamespace(delta=-240)),-2)
        self.assertEqual(wheel_steps(SimpleNamespace(delta=-15)),-1)
        self.assertEqual(wheel_steps(SimpleNamespace(num=4)),1)
        self.assertEqual(wheel_steps(SimpleNamespace(num=5)),-1)
