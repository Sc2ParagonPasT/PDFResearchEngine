"""Reader for screened library derivatives. No original-document rendering.
The renderer is a bounded same-user child process, NOT an OS security sandbox.
"""
import base64
import json
import math
import re
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import security as sec

MAX_RENDER_PIXELS=2_000_000
MAX_PNG_BYTES=8_000_000
MAX_PAGE_TEXT=40_000
ACTIVE='Screened / OCR indexed'

def validate_stage(root,folder,digest):
    root=Path(root).resolve();folder=Path(folder).resolve()
    if folder.parent!=(root/'staging').resolve() or not re.fullmatch('[a-f0-9]{64}',digest):
        raise sec.Blocked('Invalid reader staging location')
    if digest not in sec.ScreenedLibrary(root).active_digests():
        raise sec.Blocked('Document is not an active screened library item')
    src=folder/'input.quarantine';cached=root/'processed'/(digest+'.screened')
    if src.is_symlink() or cached.is_symlink():raise sec.Blocked('Invalid derivative path','suspicious')
    sec.file_check(src);sec.file_check(cached)
    if sec.sha256(src)!=digest or sec.sha256(cached)!=digest:
        raise sec.Blocked('Reader derivative has changed','suspicious')
    report=folder/'result.json'
    if not report.is_file() or report.stat().st_size>2_000_000:
        raise sec.Blocked('Missing reader rescan evidence')
    r=json.loads(report.read_text(encoding='utf-8'))
    if (r.get('verdict')!='passed' or r.get('input_sha256')!=digest or r.get('output_sha256')!=digest or
        r.get('definitions')!=sec.db_state(root/'definitions') or r.get('rules_sha256')!=sec.sha256(sec.RULES)):
        raise sec.Blocked('Reader rescan evidence does not match the current policy','suspicious')
    return src

def render_worker(root,folder,digest,page,zoom):
    sec.require_standard_user()
    page=int(page);zoom=float(zoom)
    if not 1<=page<=sec.MAX_PAGES or not math.isfinite(zoom) or not .5<=zoom<=3:
        raise sec.Blocked('Reader page or zoom outside limits')
    src=validate_stage(root,folder,digest)
    import pymupdf as f
    with f.open(str(src),filetype='pdf') as doc:
        sec.inspect_document(doc)
        if page>doc.page_count:raise sec.Blocked('Page is outside the document')
        p=doc[page-1];w,h=p.rect.width,p.rect.height
        if not 0<w<=5000 or not 0<h<=5000:raise sec.Blocked('Page dimensions outside limits')
        scale=min(zoom,math.sqrt(MAX_RENDER_PIXELS/(w*h))*.99,2500/max(w,h))
        pix=p.get_pixmap(matrix=f.Matrix(scale,scale),colorspace=f.csRGB,alpha=False,annots=False)
        if pix.width*pix.height>MAX_RENDER_PIXELS:raise sec.Blocked('Reader pixel limit exceeded')
        image=pix.tobytes('png')
        if not 0<len(image)<=MAX_PNG_BYTES:raise sec.Blocked('Reader image size limit exceeded')
        info={'digest':digest,'page':page,'pages':doc.page_count,'zoom':zoom,'scale':scale,
              'width':pix.width,'height':pix.height,'text':p.get_text('text')[:MAX_PAGE_TEXT]}
    if sec.sha256(src)!=digest:raise sec.Blocked('Reader input changed','suspicious')
    folder=Path(folder);(folder/'reader.png').write_bytes(image)
    (folder/'reader.json').write_text(json.dumps(info,ensure_ascii=True),encoding='utf-8')
    return info

def worker_main(args):
    try:render_worker(*args);return 0
    except Exception as e:
        try:(Path(args[1])/'reader-error.json').write_text(json.dumps({'reason':str(e)[:300]}),encoding='utf-8')
        except Exception:pass
        return 1

def read_page(pipe,library,digest,page,zoom):
    if digest not in library.active_digests():raise sec.Blocked('Document is not an active screened library item')
    pipe.ensure_ready()
    with pipe.checked_derivative(digest) as (staged,evidence):
        folder=staged.parent
        cmd=[sys.executable]
        if not getattr(sys,'frozen',False):cmd.append(str(sec.BASE/'app.py'))
        cmd+=['--reader-page',str(pipe.root.resolve()),str(folder.resolve()),digest,str(page),str(zoom)]
        rc,_=sec.run(cmd,60,cwd=folder)
        report=folder/'reader.json';png=folder/'reader.png'
        if rc!=0:
            err=folder/'reader-error.json'
            reason='Reader worker failed or timed out'
            if err.is_file() and err.stat().st_size<4096:
                try:reason=str(json.loads(err.read_text(encoding='utf-8')).get('reason',reason))[:300]
                except ValueError:pass
            raise sec.Blocked(reason,'unavailable')
        if not report.is_file() or report.stat().st_size>500000 or not png.is_file() or png.stat().st_size>MAX_PNG_BYTES:
            raise sec.Blocked('Reader response outside limits','unavailable')
        info=json.loads(report.read_text(encoding='utf-8'));image=png.read_bytes()
        if (info.get('digest')!=digest or info.get('page')!=page or info.get('zoom')!=zoom or
            type(info.get('pages')) is not int or not page<=info['pages']<=sec.MAX_PAGES or
            type(info.get('width')) is not int or type(info.get('height')) is not int or
            not 0<info['width']*info['height']<=MAX_RENDER_PIXELS or
            not image.startswith(b'\x89PNG\r\n\x1a\n') or sec.sha256(staged)!=digest or
            not isinstance(info.get('text'),str) or len(info['text'])>MAX_PAGE_TEXT):
            raise sec.Blocked('Reader response did not match screened document','suspicious')
        # Validate PNG IHDR dimensions before handing the bounded image to Tk.
        if len(image)<33 or image[12:16]!=b'IHDR' or int.from_bytes(image[16:20],'big')!=info['width'] or int.from_bytes(image[20:24],'big')!=info['height']:
            raise sec.Blocked('Reader image dimensions did not match evidence','suspicious')
        return info,image

class ReaderWindow:
    def __init__(self,app):
        self.app=app;self.digest=None;self.title='';self.pages=1;self.page=1;self.zoom=1.25
        self.win=tk.Toplevel(app.win);self.win.title('Screened PDF reader');self.win.geometry('1050x850');self.win.configure(bg='#11151b')
        self.win.protocol('WM_DELETE_WINDOW',self.win.withdraw)
        f=ttk.Frame(self.win,padding=10);f.pack(fill='both',expand=True)
        self.caption=tk.StringVar(value='No document selected');ttk.Label(f,textvariable=self.caption,wraplength=980).pack(fill='x',pady=5)
        bar=ttk.Frame(f);bar.pack(fill='x',pady=4)
        ttk.Button(bar,text='Previous',command=lambda:self.go(self.page-1)).pack(side='left')
        self.pagevar=tk.StringVar(value='1');entry=ttk.Entry(bar,textvariable=self.pagevar,width=5);entry.pack(side='left',padx=4);entry.bind('<Return>',lambda e:self.jump())
        self.total=tk.StringVar(value='/ 1');ttk.Label(bar,textvariable=self.total).pack(side='left')
        ttk.Button(bar,text='Go',command=self.jump).pack(side='left',padx=4)
        ttk.Button(bar,text='Next',command=lambda:self.go(self.page+1)).pack(side='left')
        ttk.Button(bar,text='Zoom -',command=lambda:self.change_zoom(-.25)).pack(side='left',padx=4)
        ttk.Button(bar,text='Zoom +',command=lambda:self.change_zoom(.25)).pack(side='left')
        ttk.Button(bar,text='Fit',command=self.fit).pack(side='left',padx=4)
        ttk.Button(bar,text='Full screen',command=self.fullscreen).pack(side='right')
        self.win.bind('<Escape>',lambda e:self.win.attributes('-fullscreen',False))
        search=ttk.Frame(f);search.pack(fill='x',pady=4)
        self.query=tk.StringVar();q=ttk.Entry(search,textvariable=self.query);q.pack(side='left',fill='x',expand=True);q.bind('<Return>',lambda e:self.find())
        ttk.Button(search,text='Find in indexed text',command=self.find).pack(side='left',padx=4)
        self.status=tk.StringVar(value='Select a screened library document.');ttk.Label(f,textvariable=self.status,wraplength=980).pack(fill='x',pady=4)
        pane=ttk.Panedwindow(f,orient='vertical');pane.pack(fill='both',expand=True)
        frame=ttk.Frame(pane);pane.add(frame,weight=5)
        self.canvas=tk.Canvas(frame,bg='#11151b',highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew');frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        y=ttk.Scrollbar(frame,orient='vertical',command=self.canvas.yview);y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(frame,orient='horizontal',command=self.canvas.xview);x.grid(row=1,column=0,sticky='ew')
        self.canvas.configure(xscrollcommand=x.set,yscrollcommand=y.set)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units'))
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-3,'units'))
        self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(3,'units'))
        lower=ttk.Frame(pane);pane.add(lower,weight=1)
        ttk.Label(lower,text='Searchable page text (select and copy)').pack(anchor='w')
        self.text=app.text(lower,5);self.text.pack(fill='both',expand=True);self.text.configure(state='disabled')
        self.photo=None;self.intrinsic=None
    def open(self,digest,title,pages):
        self.digest=digest;self.title=title;self.pages=max(1,int(pages));self.zoom=1.25;self.intrinsic=None
        last=self.app.prefs.get('reader_pages',{})
        try:page=max(1,min(self.pages,int(last.get(digest,1))))
        except (ValueError,TypeError,AttributeError):page=1
        self.caption.set(title);self.total.set('/ '+str(self.pages));self.win.deiconify();self.win.lift()
        self.go(page)
    def fullscreen(self):
        self.win.attributes('-fullscreen',not self.win.attributes('-fullscreen'))
    def jump(self):
        try:self.go(int(self.pagevar.get()))
        except ValueError:messagebox.showinfo('Page','Enter a valid page number.',parent=self.win)
    def set_zoom(self,value):
        if self.app.busy:return
        self.zoom=max(.5,min(3,value));self.go(self.page)
    def fit(self):
        if self.intrinsic:
            w,h=self.intrinsic;self.set_zoom(min(self.canvas.winfo_width()/w,self.canvas.winfo_height()/h))
        else:self.set_zoom(1.0)
    def change_zoom(self,delta):self.set_zoom(self.zoom+delta)
    def find(self):
        if self.app.busy or not self.digest:return
        needle=self.query.get().strip().casefold()
        if not needle:return
        body=self.app.lib.text(self.digest)
        chunks=re.split(r'\[Page (\d+)\]',body)
        pages=[int(chunks[i]) for i in range(1,len(chunks)-1,2) if needle in chunks[i+1].casefold()]
        if not pages:self.status.set('No match in the stored OCR index.');return
        self.go(next((p for p in pages if p>self.page),pages[0]))
    def go(self,page):
        if not self.digest:return
        if self.app.busy:self.status.set('Wait for the current operation to finish.');return
        if not 1<=page<=self.pages:self.status.set('Page is outside the document.');return
        digest=self.digest;zoom=self.zoom
        self.status.set('Checking identity, rescanning and rendering the screened derivative…')
        self.canvas.delete('all');self.photo=None
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.configure(state='disabled')
        pipe=self.app.pipeline()
        def work():
            try:self.app.events.put(('reader_result',(digest,read_page(pipe,self.app.lib,digest,page,zoom))))
            except sec.Blocked as e:
                if e.verdict in ('malware','suspicious'):self.app.lib.blocked(digest,str(e));self.app.events.put(('library',None))
                self.app.events.put(('reader_error',(digest,str(e))))
            except Exception as e:self.app.events.put(('reader_error',(digest,str(e))))
        self.app.start(work)
    def event(self,k,v):
        digest,data=v
        if digest!=self.digest:return
        if k=='reader_error':
            self.status.set('Reader blocked: '+str(data)[:300]);return
        info,image=data
        try:
            self.photo=tk.PhotoImage(master=self.win,data=base64.b64encode(image),format='png')
            self.canvas.delete('all');self.canvas.create_image(0,0,image=self.photo,anchor='nw');self.canvas.configure(scrollregion=(0,0,self.photo.width(),self.photo.height()))
            self.canvas.xview_moveto(0);self.canvas.yview_moveto(0)
            self.intrinsic=(info['width']/info['scale'],info['height']/info['scale'])
            self.page=info['page'];self.pages=info['pages'];self.pagevar.set(str(self.page));self.total.set('/ '+str(self.pages))
            self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',info['text']);self.text.configure(state='disabled')
            self.status.set(f'Page {self.page} of {self.pages} • rendered at {info["scale"]*100:.0f}% • fresh rescan passed')
            last=self.app.prefs.get('reader_pages',{})
            if not isinstance(last,dict):last={}
            last.pop(digest,None);last[digest]=self.page;self.app.prefs['reader_pages']=dict(list(last.items())[-200:]);self.app.persist()
        except tk.TclError as e:self.status.set('Could not display the bounded page image: '+str(e)[:150])
