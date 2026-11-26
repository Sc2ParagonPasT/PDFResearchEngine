"""Packaged executable diagnostics; uses generated, harmless local fixtures only."""
from pathlib import Path
import json, tempfile, hashlib, shutil
from engine import Result
from security import component, run, dependencies, reconstruct, Pipeline, Blocked, sha256

def diagnostics(output,live=False):
    output=Path(output);checks={}
    try:
        # FreshClam on Windows reads a configuration file even for --version.
        # A temporary valid config avoids modifying the bundled vendor files.
        with tempfile.TemporaryDirectory(prefix='pdfresearch-version-') as td:
            root=Path(td)
            config=root/'freshclam.conf'
            db=root/'definitions';db.mkdir()
            config.write_text('DatabaseMirror database.clamav.net\nChecks 12\nConnectTimeout 15\nReceiveTimeout 120\n',encoding='utf-8')
            for name in ('clamscan','freshclam'):
                args=[component(name),'--version']
                if name=='freshclam':
                    args += ['--config-file='+str(config.resolve()),'--datadir='+str(db.resolve())]
                rc,text=run(args,30,cwd=root)
                if rc!=0:raise RuntimeError(name+' did not start: '+text[-500:])
                checks[name]=text.strip()[:200]
        rules=dependencies()
        if not rules.match(data=b'%PDF-1.7\n/Launch /HarmlessDiagnostic\n%%EOF\n',timeout=10):raise RuntimeError('YARA diagnostic rule did not match')
        checks['yara']='Compiled and matched a harmless PDF policy fixture'
        import pymupdf
        with tempfile.TemporaryDirectory(prefix='pdfresearch-diagnostic-') as td:
            root=Path(td);fixture=root/'fixture.quarantine';derivative=root/'fixture.pending'
            with pymupdf.open() as doc:
                p=doc.new_page(width=400,height=200);p.insert_text((20,45),'Research engine diagnostic',fontsize=15);doc.save(str(fixture))
            text,pages,searchable=reconstruct(fixture,derivative)
            if not searchable or 'research engine diagnostic' not in text.lower():raise RuntimeError('OCR diagnostic failed')
            checks['ocr']='Generated searchable raster derivative'
            if live:
                pipe=Pipeline(root/'appdata');pipe.ensure_ready()
                class LocalFixture:
                    def download(self,url,folder):
                        digest=sha256(fixture);p=Path(folder)/(digest+'.quarantine');shutil.copyfile(fixture,p);return p,digest,p.stat().st_size,url
                r=pipe.process(LocalFixture(),Result('Diagnostic','https://www.cia.gov/diagnostic.pdf','local fixture'))
                if r['verdict']!='passed':raise RuntimeError('Live inspection failed: '+str(r))
                destination=root/'export';destination.mkdir();target=pipe.export(r['output_sha256'],destination)
                if sha256(target)!=r['output_sha256']:raise RuntimeError('Export digest mismatch')
                checks['live']='FreshClam update, actual dual-engine scans, OCR and export succeeded on benign local fixture'
        report={'status':'passed','checks':checks,'live_requested':live}
    except Exception as e:report={'status':'failed','checks':checks,'error':str(e)[:1000],'live_requested':live}
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report['status']=='passed'
