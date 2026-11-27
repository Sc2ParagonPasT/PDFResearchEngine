"""Apply the scanner temp-directory correction to the hash-verified v0.2 source."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / "security.py"
s = p.read_text(encoding="utf-8")
old = """    rc,out=run([component('clamscan'),'--database='+str(Path(db).resolve()),'--stdout',
                '--alert-exceeds-max=yes','--alert-encrypted=yes','--max-filesize=60M',
                '--max-scansize=200M','--max-scantime=120000','--bytecode=yes',str(Path(path).resolve())],150,cwd=Path(path).parent)"""
new = """    path=Path(path).resolve()
    # Use an existing, writable, per-scan directory rather than inherited OS temp paths.
    with tempfile.TemporaryDirectory(prefix='clam-',dir=path.parent) as scan_tmp:
        rc,out=run([component('clamscan'),'--database='+str(Path(db).resolve()),'--stdout',
                    '--tempdir='+str(Path(scan_tmp).resolve()),
                    '--alert-exceeds-max=yes','--alert-encrypted=yes','--max-filesize=60M',
                    '--max-scansize=200M','--max-scantime=120000','--bytecode=yes',str(path)],150,cwd=path.parent)"""
assert s.count(old) == 1, "Unexpected ClamAV invocation"
s = s.replace(old, new)
old = r"or re.search(r'(?im)^\s*(?:ERROR|WARNING):',out):"
new = r"or re.search(r'(?im)^\s*(?:ERROR|WARNING):|^Total errors:\s*[1-9][0-9]*\s*$',out):"
assert s.count(old) == 1, "Unexpected scan-result validation"
p.write_text(s.replace(old, new), encoding="utf-8")

p = root / "test_security.py"
s = p.read_text(encoding="utf-8")
marker = '    def test_clam_heuristic_not_definitive_malware(self):'
test = """    def test_clam_uses_writable_per_scan_temp_and_blocks_errors(self):
        p=self.root/'fixture';p.write_bytes(SAMPLE);seen=[]
        def scan(args,timeout,cwd=None):
            dirs=[a.split('=',1)[1] for a in args if a.startswith('--tempdir=')]
            self.assertEqual(len(dirs),1);d=Path(dirs[0]);seen.append(d)
            self.assertEqual(d.parent,p.parent.resolve());self.assertTrue(d.is_dir())
            (d/'probe').write_text('writable')
            return 0,'Scanned files: 1\\nInfected files: 0\\nTotal errors: 1'
        with patch('security.component',return_value='fake-clamscan'),patch('security.run',side_effect=scan):
            with self.assertRaises(s.Blocked) as ex:s.clam_scan(p,self.root/'definitions')
        self.assertEqual(ex.exception.verdict,'unavailable');self.assertFalse(seen[0].exists())
"""
assert s.count(marker) == 1, "Unexpected test source"
p.write_text(s.replace(marker, test + marker), encoding="utf-8")
print("Applied ClamAV per-scan temporary directory and stricter error validation.")
