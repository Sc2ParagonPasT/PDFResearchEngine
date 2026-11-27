"""v0.4 desktop usability layer; all native security decisions remain in Pipeline."""
import dataclasses
import datetime as dt
import os
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from pathlib import Path
from desktop_helpers import safe_pdf_name, export_folder, load_preferences, save_preferences
from discovery_v03 import Network, VERIFIED, run_search
from catalog_v04 import CATALOG, BY_KEY, Index, search_catalog
from security import Pipeline, Blocked

BG='#11151b'; PANEL='#1b222c'; FG='#e5eaf2'; MUTED='#a3b0c2'
ACTIVE='Screened / OCR indexed'

def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)

def reveal(folder):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError('Folder is unavailable: '+str(folder))
    if os.name=='nt':os.startfile(str(folder))
    else:subprocess.Popen(['xdg-open',str(folder)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

class Monitor:
    def __init__(self,app):
        self.app=app;self.win=tk.Toplevel(app.win);self.win.title('Processing Monitor')
        self.win.configure(bg=BG);self.win.geometry('880x650');self.win.minsize(540,420)
        self.win.protocol('WM_DELETE_WINDOW',self.win.withdraw)
        box=ttk.Frame(self.win,padding=14);box.pack(fill='both',expand=True)
        self.head=tk.StringVar();self.summary=tk.StringVar()
        ttk.Label(box,textvariable=self.head,wraplength=760).pack(fill='x',pady=5)
        ttk.Label(box,textvariable=self.summary,wraplength=760).pack(fill='x',pady=4)
        self.bar=ttk.Progressbar(box,mode='determinate');self.bar.pack(fill='x',pady=5)
        self.table=ttk.Treeview(box,columns=('title','outcome'),show='headings',height=7)
        for key,title,width in [('title','Document',470),('outcome','Outcome',240)]:
            self.table.heading(key,text=title);self.table.column(key,width=width,minwidth=100)
        self.table.pack(fill='both',expand=True,pady=5)
        logframe=ttk.Frame(box);logframe.pack(fill='both',expand=True)
        self.log=app.text(logframe,8);self.log.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(logframe,command=self.log.yview);sb.pack(side='right',fill='y');self.log.configure(yscrollcommand=sb.set,state='disabled')
        controls=ttk.Frame(box);controls.pack(fill='x',pady=8)
        self.cancel=ttk.Button(controls,text='Cancel remaining',command=app.stop.set);self.cancel.pack(side='left')
        ttk.Button(controls,text='Open export folder',command=app.open_export).pack(side='left',padx=6)
        ttk.Button(controls,text='Minimize',command=self.win.withdraw).pack(side='right')
        self.rows=[];self.states=[]
        self.win.bind('<Configure>',lambda e:self._wrap(e))
    def _wrap(self,e):
        if e.widget==self.win:
            for w in walk(self.win):
                if isinstance(w,ttk.Label):w.configure(wraplength=max(260,e.width-45))
    def begin(self,titles):
        self.table.delete(*self.table.get_children());self.rows=[];self.states=['Queued']*len(titles)
        for title in titles:self.rows.append(self.table.insert('','end',values=(title,'Queued')))
        self.bar.configure(maximum=max(1,len(titles)),value=0);self.head.set('Preparing mandatory security checks')
        self.log.configure(state='normal');self.log.delete('1.0','end');self.log.configure(state='disabled')
        self.cancel.configure(state='normal');self.counts();self.show()
    def show(self):
        self.win.deiconify();self.win.lift()
    def counts(self):
        counts={s:self.states.count(s) for s in ('Completed','Active','Blocked','Failed','Cancelled','Queued')}
        self.summary.set(' | '.join(f'{k}: {v}' for k,v in counts.items()))
        self.bar.configure(value=sum(counts[x] for x in ('Completed','Blocked','Failed','Cancelled')))
    def event(self,kind,value):
        if kind=='batch_row':
            i,state,detail=value
            self.states[i]=state;self.table.set(self.rows[i],'outcome',state);self.table.see(self.rows[i])
            self.head.set(f'Document {i+1} of {len(self.rows)}: {detail}');self.counts();self.append(detail)
        elif kind=='batch_log':self.head.set(str(value)[:300]);self.append(value)
        elif kind=='batch_end':
            for i,s in enumerate(self.states):
                if s=='Queued':self.states[i]='Cancelled';self.table.set(self.rows[i],'outcome','Cancelled')
            self.counts();self.cancel.configure(state='disabled');self.head.set('Batch finished. Review each document outcome.');self.append('Batch finished.')
    def append(self,msg):
        self.log.configure(state='normal');self.log.insert('end',dt.datetime.now().strftime('%H:%M:%S')+'  '+str(msg)[:500]+'\n');self.log.see('end');self.log.configure(state='disabled')

def desktop_class(Base):
    class Desktop(Base):
        def style(self):
            super().style()
            self.prefpath=self.root/'desktop-v04.json';self.prefs=load_preferences(self.prefpath)
            try:size=max(10,min(24,int(self.prefs.get('text_size',13))))
            except (ValueError,TypeError):size=13
            self.normalfont=font.Font(self.win,family='Segoe UI',size=size)
            self.titlefont=font.Font(self.win,family='Segoe UI',size=size+7,weight='bold')
            self.textsize=tk.IntVar(value=size)
            self.sizeset=None;self.monitor=None
            self.apply_fonts()
        def apply_fonts(self,*_):
            size=int(self.textsize.get())
            self.normalfont.configure(size=size);self.titlefont.configure(size=size+7)
            s=ttk.Style(self.win);s.configure('.',font=self.normalfont);s.configure('Title.TLabel',font=self.titlefont)
            s.configure('Treeview',font=self.normalfont,rowheight=self.normalfont.metrics('linespace')+10)
            s.configure('Treeview.Heading',font=self.normalfont)
            s.configure('TButton',padding=(6,4));s.configure('TNotebook.Tab',padding=(9,5))
            self.win.option_add('*Font',str(self.normalfont))
            for w in walk(self.win):
                if isinstance(w,(tk.Text,tk.Entry,tk.Listbox,tk.Checkbutton,tk.Label,tk.Button)):
                    w.configure(font=self.normalfont)
                elif isinstance(w,ttk.Label) and str(w.cget('style'))=='Title.TLabel':
                    w.configure(font=self.titlefont)
            self.prefs['text_size']=size
            if self.sizeset is not None:self.win.after_cancel(self.sizeset)
            self.sizeset=self.win.after(350,self.persist)
        def persist(self):
            self.sizeset=None
            try:save_preferences(self.prefpath,self.prefs)
            except OSError as e:self.status.set('Could not save preferences: '+str(e)) if hasattr(self,'status') else None
        def text(self,parent,height=6):
            w=super().text(parent,height);w.configure(font=self.normalfont);return w
        def layout(self):
            super().layout()
            self.catalog_index=Index(self.root/'discovery-v04.sqlite3')
            self.catalog_keys=set(self.prefs.get('catalog_enabled',[]))&set(BY_KEY)
            self.win.title('PDF Research Engine | v0.4 development')
            self.win.geometry('1320x900')
            shell=self.win.winfo_children()[0]
            header=ttk.Frame(shell);header.pack(fill='x',before=shell.winfo_children()[0],pady=(0,8))
            ttk.Label(header,text='Text size').pack(side='left')
            ttk.Scale(header,from_=10,to=24,variable=self.textsize,command=lambda v:self.resize_text(v)).pack(side='left',fill='x',expand=True,padx=8)
            ttk.Label(header,textvariable=self.textsize,width=3).pack(side='left')
            ttk.Button(header,text='Reset',command=lambda:self.resize_text(13)).pack(side='left',padx=5)
            ttk.Button(header,text='Quick Start Guide',command=self.welcome).pack(side='right')
            ttk.Button(header,text='Processing Monitor',command=self.show_monitor).pack(side='right',padx=5)
            ttk.Button(header,text='Source Catalog',command=self.catalog_window).pack(side='right',padx=5)
            self.searchbtn.configure(text='Search')
            for w in walk(self.discovery):
                if isinstance(w,ttk.Entry) and str(w.cget('textvariable'))==str(self.q):
                    w.bind('<Return>',lambda e:self.search())
            self.searchprogress=tk.StringVar(value='Enter a topic to search.')
            progress=ttk.Label(self.discovery,textvariable=self.searchprogress,wraplength=1100)
            progress.pack(fill='x',before=self.tree.master,pady=(0,6))
            libbar=ttk.Frame(self.library);libbar.pack(fill='x',before=self.lt.master,pady=(0,6))
            ttk.Button(libbar,text='Open Library Folder',command=self.open_library).grid(row=0,column=0,sticky='w')
            ttk.Button(libbar,text='Open Export Folder',command=self.open_export).grid(row=0,column=1,sticky='w',padx=4)
            ttk.Button(libbar,text='Choose Export Folder',command=self.choose_export).grid(row=0,column=2,sticky='w',padx=4)
            self.autoexport=tk.BooleanVar(value=bool(self.prefs.get('auto_export',False)))
            ttk.Checkbutton(libbar,text='Automatically export after final rescan',variable=self.autoexport,command=self.store_auto).grid(row=1,column=0,columnspan=3,sticky='w',pady=3)
            self.pathlabel=tk.StringVar()
            ttk.Label(libbar,textvariable=self.pathlabel,wraplength=1100).grid(row=2,column=0,columnspan=3,sticky='w')
            self.update_paths()
            self.action_buttons=[]
            for w in walk(self.win):
                if isinstance(w,ttk.Button) and w.cget('text') in ('Inspect & index selected','Recheck PDF access','Rescan & export PDF','Recheck library','Check security','Update definitions'):
                    self.action_buttons.append(w)
            self.apply_fonts()
            if not self.prefs.get('hide_welcome',False):self.win.after(350,self.welcome)
        def resize_text(self,v):
            self.textsize.set(max(10,min(24,round(float(v)))));self.apply_fonts()
        def update_paths(self):
            self.pathlabel.set('Internal library: '+str(self.root/'processed')+'\nPDF exports: '+str(export_folder(self.prefs.get('last_folder'))))
        def open_library(self):
            try:
                p=self.root/'processed';p.mkdir(exist_ok=True);reveal(p)
            except Exception as e:messagebox.showerror('Library folder',str(e),parent=self.win)
        def open_export(self):
            try:reveal(export_folder(self.prefs.get('last_folder')))
            except Exception as e:messagebox.showerror('Export folder',str(e),parent=self.win)
        def choose_export(self):
            p=filedialog.askdirectory(initialdir=str(export_folder(self.prefs.get('last_folder'))),mustexist=True,parent=self.win)
            if p:self.prefs['last_folder']=p;self.persist();self.update_paths()
        def store_auto(self):
            self.prefs['auto_export']=self.autoexport.get();self.persist()
        def welcome(self):
            if getattr(self,'guide',None) and self.guide.winfo_exists():self.guide.lift();return
            w=self.guide=tk.Toplevel(self.win);w.title('Welcome to PDF Research Engine');w.geometry('780x650');w.configure(bg=BG)
            f=ttk.Frame(w,padding=18);f.pack(fill='both',expand=True)
            ttk.Label(f,text='Start researching',style='Title.TLabel').pack(anchor='w')
            body=self.text(f,12);body.pack(fill='both',expand=True,pady=10)
            body.insert('1.0','SEARCH\nType a topic and press Enter or click Search. The app checks candidate PDF links before showing them.\n\nINSPECT\nSelect one or more results and choose Inspect & index selected. Watch the Processing Monitor for download, scanning and OCR progress. Blocked files are not released.\n\nLIBRARY\nOpen Local library to find searchable text and processed documents. Open Library Folder shows internal .screened files.\n\nSAVE\nUse Rescan & export PDF to save a normal PDF using the publication title. Choose an export folder and optionally enable automatic export.\n\nCUSTOMIZE\nUse the header text-size slider. Source Catalog contains built-in independent, historical, scientific and other collections. Enable them once, rather than typing website addresses. Unvalidated sources may not return results. Security screening reduces risk but cannot guarantee that documents are harmless. This experimental application is not an OS sandbox.')
            body.configure(state='disabled')
            hide=tk.BooleanVar(value=bool(self.prefs.get('hide_welcome',False)))
            ttk.Checkbutton(f,text="Don't show this again",variable=hide).pack(anchor='w')
            def done():
                self.prefs['hide_welcome']=hide.get();self.persist();w.destroy()
            buttons=ttk.Frame(f);buttons.pack(fill='x',pady=8)
            ttk.Button(buttons,text='Explore built-in sources',command=self.catalog_window).pack(side='left')
            ttk.Button(buttons,text='Start Researching',command=done).pack(side='right')
            w.protocol('WM_DELETE_WINDOW',done);w.bind('<Escape>',lambda e:done())
        def show_monitor(self):
            if self.monitor is None:self.monitor=Monitor(self)
            self.monitor.show()
        def batch(self,titles,fn):
            if self.busy:messagebox.showinfo('Busy','Stop or finish the current operation first.');return
            self.show_monitor();self.monitor.begin(titles)
            def work():
                try:fn()
                finally:self.events.put(('batch_end',None))
            self.start(work)
        def start(self,fn):
            ok=super().start(fn)
            if ok:
                self.searchbtn.configure(text='Working…')
                for w in self.action_buttons:w.configure(state='disabled')
            return ok
        def catalog_window(self):
            if getattr(self,'catalogwin',None) and self.catalogwin.winfo_exists():self.catalogwin.lift();return
            w=self.catalogwin=tk.Toplevel(self.win);w.title('Built-in Source Catalog');w.geometry('1050x680');w.configure(bg=BG)
            f=ttk.Frame(w,padding=12);f.pack(fill='both',expand=True)
            ttk.Label(f,text=f'{len(CATALOG)} collection candidates • operational status varies',style='Title.TLabel',wraplength=980).pack(anchor='w')
            ttk.Label(f,text='Choose collections once. Search automatically prioritizes up to eight relevant enabled collections per query in addition to the established search adapters. A reachable PDF is not yet security-screened.',wraplength=980).pack(fill='x',pady=6)
            query=tk.StringVar();ttk.Entry(f,textvariable=query).pack(fill='x')
            frame=ttk.Frame(f);frame.pack(fill='both',expand=True,pady=6)
            tree=ttk.Treeview(frame,columns=('name','category','enabled','status'),show='headings',selectmode='extended')
            for key,title,width in [('name','Collection',340),('category','Subject area',230),('enabled','Enabled',90),('status','Last local test',300)]:
                tree.heading(key,text=title);tree.column(key,width=width,minwidth=70)
            tree.pack(side='left',fill='both',expand=True)
            sb=ttk.Scrollbar(frame,command=tree.yview);sb.pack(side='right',fill='y');tree.configure(yscrollcommand=sb.set)
            def refresh(*_):
                tree.delete(*tree.get_children());states=self.catalog_index.states()
                for source in CATALOG:
                    if query.get().lower() not in (source.name+' '+source.category+' '+source.tags).lower():continue
                    state=states.get(source.key)
                    status=state[3] if state else 'Not validated'
                    tree.insert('','end',iid=source.key,values=(source.name,source.category,'Yes' if source.key in self.catalog_keys else 'No',status))
            query.trace_add('write',refresh);refresh()
            def enable(keys):
                if self.busy:messagebox.showinfo('Busy','Wait until the current operation finishes.',parent=w);return
                keys=set(keys)&set(BY_KEY)
                hosts=sorted({host for key in keys for host in BY_KEY[key].hosts}-set(self.hosts))
                if hosts:
                    approval=tk.Toplevel(w);approval.title('Authorize exact HTTPS domains');approval.geometry('760x550');approval.transient(w);approval.grab_set()
                    panel=ttk.Frame(approval,padding=12);panel.pack(fill='both',expand=True)
                    ttk.Label(panel,text='These exact domains will be authorized for research requests. This is not a statement about their reliability or safety. All PDFs must still pass security inspection.',wraplength=700).pack(fill='x')
                    body=self.text(panel,12);body.pack(fill='both',expand=True,pady=8);body.insert('1.0','\n'.join(hosts));body.configure(state='disabled')
                    accepted=tk.BooleanVar(value=False)
                    def yes():accepted.set(True);approval.destroy()
                    ttk.Button(panel,text='Authorize listed domains',command=yes).pack(side='right')
                    ttk.Button(panel,text='Cancel',command=approval.destroy).pack(side='right',padx=6)
                    w.wait_window(approval)
                    if not accepted.get():return
                    try:
                        cfg=load_preferences(self.config);cfg.update({'hosts':sorted(set(self.hosts)|set(hosts)),'seeds':self.seeds,'threat_action':self.threat_action,'auto_rescan':self.auto_rescan})
                        save_preferences(self.config,cfg);self.hosts=cfg['hosts']
                        self.hosttext.delete('1.0','end');self.hosttext.insert('1.0','\n'.join(self.hosts))
                    except Exception as e:messagebox.showerror('Source approval',str(e),parent=w);return
                self.catalog_keys.update(keys);self.prefs['catalog_enabled']=sorted(self.catalog_keys);self.persist();refresh()
            def disable():
                if self.busy:messagebox.showinfo('Busy','Wait until the current operation finishes.',parent=w);return
                self.catalog_keys.difference_update(tree.selection());self.prefs['catalog_enabled']=sorted(self.catalog_keys);self.persist();refresh()
            buttons=ttk.Frame(f);buttons.pack(fill='x',pady=5)
            ttk.Button(buttons,text='Enable all built-in collections',command=lambda:enable(BY_KEY)).pack(side='left')
            ttk.Button(buttons,text='Enable selected',command=lambda:enable(tree.selection())).pack(side='left',padx=5)
            ttk.Button(buttons,text='Disable selected',command=disable).pack(side='left')
            ttk.Button(buttons,text='Refresh status',command=refresh).pack(side='right')
        def search(self):
            if self.busy:messagebox.showinfo('Busy','Wait for the current operation or click Stop.');return
            if self.generated_query!=self.q.get() or self.generated_depth!=self.depth.get():self.generate()
            terms=list(dict.fromkeys(x.strip()[:240] for x in self.termtext.get('1.0','end').splitlines() if x.strip()))[:24]
            providers=[p for p,v in self.providers.items() if v.get()];seeds=self.seeds if self.crawlvar.get() else []
            keys=set(self.catalog_keys)
            if not terms or not (providers or seeds or keys):messagebox.showinfo('Search','Enter a topic and enable a source.');return
            self.tree.delete(*self.tree.get_children());self.results.clear();net=Network(self.hosts)
            def work():
                seen=set()
                def emit(k,v):
                    if k=='result':
                        if v.url in seen:return
                        seen.add(v.url)
                    if k!='done':self.events.put((k,v))
                if providers or seeds:run_search(net,providers,terms,seeds,self.stop,emit)
                if keys and not self.stop.is_set():search_catalog(net,keys,terms,self.catalog_index,self.stop,emit,set(seen))
                self.events.put(('done',f'{len(seen)} reachable PDFs; mandatory security inspection still required'+(' (stopped)' if self.stop.is_set() else '')))
            if self.start(work):self.searchbtn.configure(text='Searching…');self.searchprogress.set('Searching and verifying PDF candidates…')
        def selected_action(self,action):
            if self.busy:messagebox.showinfo('Busy','Stop or finish the current search first.');return
            ids=self.tree.selection()
            if not ids:messagebox.showinfo('Select documents','Select one or more results first.');return
            if action!='download':return super().selected_action(action)
            if len(ids)>30:messagebox.showinfo('Batch limit','Select up to 30 documents.');return
            selected=[(i,dataclasses.replace(self.results[i])) for i in ids]
            auto=self.autoexport.get();folder=export_folder(self.prefs.get('last_folder'));net=Network(self.hosts)
            emit=lambda k,v:self.events.put((k,v))
            pipe=Pipeline(self.root,self.threat_action,progress=lambda msg:emit('batch_log',msg))
            def work():
                try:emit('health',pipe.ensure_ready())
                except Exception as e:
                    for j,(_,r) in enumerate(selected):emit('batch_row',(j,'Failed','Security unavailable: '+str(e)))
                    return
                for j,(i,r) in enumerate(selected):
                    if self.stop.is_set():break
                    emit('batch_row',(j,'Active',r.title));r.status='Retrieving / inspecting';emit('update',(i,dataclasses.replace(r)))
                    outcome='Failed';detail=''
                    try:
                        e=pipe.process(net,r)
                        if e['verdict']=='passed':
                            emit('batch_log','Validated inspection evidence; indexing searchable derivative')
                            self.lib.save(r,e);r.digest=e['digest'];r.status=ACTIVE
                            outcome='Completed';detail=r.title+' — indexed'
                            if auto and not self.stop.is_set():
                                emit('batch_log','Final rescan before automatic export')
                                try:
                                    target=pipe.export(e['output_sha256'],folder,title=r.title)
                                    emit('saved_folder',str(target.parent));detail+='; exported '+str(target)
                                except Blocked as ex:
                                    if ex.verdict in ('malware','suspicious'):
                                        self.lib.blocked(e['output_sha256'],str(ex));r.status='Blocked';outcome='Blocked'
                                    else:outcome='Failed'
                                    detail+='; export denied: '+str(ex)
                                except Exception as ex:outcome='Failed';detail+='; export failed: '+str(ex)
                        else:
                            outcome='Blocked' if e['verdict'] in ('malware','suspicious','blocked') else 'Failed'
                            r.status=e['verdict'].capitalize()+' / '+e.get('disposition','blocked');detail=e.get('reason','Inspection not passed')
                    except Exception as e:r.status='Rejected / unavailable';detail=str(e)
                    emit('update',(i,r));emit('batch_row',(j,outcome,detail))
                emit('library',None)
            self.batch([r.title for _,r in selected],work)
        def export_selected(self):
            if self.busy:messagebox.showinfo('Busy','Wait for the current operation.');return
            ids=self.lt.selection()
            if not ids:messagebox.showinfo('Export','Select a library document first.');return
            docs=[];seen=set()
            for i in ids:
                digest=self.docids[i]
                if digest in seen:continue
                seen.add(digest);title,_,_,status,_=self.lt.item(i,'values')
                if status!=ACTIVE:messagebox.showerror('Export denied','Select only screened library documents.');return
                docs.append((digest,title))
            if len(docs)>30:messagebox.showinfo('Batch limit','Select up to 30 documents.');return
            folder=export_folder(self.prefs.get('last_folder'))
            if len(docs)==1:
                try:default=safe_pdf_name(docs[0][1],folder)
                except ValueError as e:messagebox.showerror('Export',str(e));return
                value=filedialog.asksaveasfilename(parent=self.win,title='Save screened PDF',initialdir=str(folder),initialfile=default,defaultextension='.pdf',filetypes=[('PDF document','*.pdf')],confirmoverwrite=False)
                if not value:return
                p=Path(value);folder=p.parent;docs=[(docs[0][0],p.name)]
            else:
                value=filedialog.askdirectory(parent=self.win,title='Export selected PDFs',initialdir=str(folder),mustexist=True)
                if not value:return
                folder=Path(value)
            emit=lambda k,v:self.events.put((k,v))
            pipe=Pipeline(self.root,self.threat_action,progress=lambda msg:emit('batch_log',msg))
            def work():
                for j,(digest,title) in enumerate(docs):
                    if self.stop.is_set():break
                    emit('batch_row',(j,'Active','Final security rescan: '+title))
                    try:
                        target=pipe.export(digest,folder,title=title)
                        emit('saved_folder',str(target.parent));emit('batch_row',(j,'Completed','Exported '+str(target)))
                    except Blocked as e:
                        outcome='Blocked' if e.verdict in ('malware','suspicious','blocked') else 'Failed'
                        if e.verdict in ('malware','suspicious'):self.lib.blocked(digest,str(e))
                        emit('batch_row',(j,outcome,str(e)))
                    except Exception as e:emit('batch_row',(j,'Failed',str(e)))
                emit('library',None)
            self.batch([t for _,t in docs],work)
        def poll(self):
            try:
                while True:
                    k,v=self.events.get_nowait()
                    if k.startswith('batch_'):
                        if self.monitor:self.monitor.event(k,v)
                    elif k=='saved_folder':
                        self.prefs['last_folder']=v;self.persist();self.update_paths()
                    elif k=='result':
                        i=self.tree.insert('','end',values=self.row(v));self.results[i]=v
                    elif k=='update':
                        i,r=v;self.results[i]=r;self.tree.item(i,values=self.row(r))
                    elif k in ('progress','done'):
                        self.status.set(v);self.searchprogress.set(v)
                    elif k=='library':self.refresh_library()
                    elif k=='health':
                        msg='Security prerequisites available; document scans still required.' if v.get('verdict')=='ready' else 'Security unavailable: '+v.get('reason','Unknown failure')
                        self.health.set(msg);self.status.set(msg)
                    elif k=='idle':
                        self.busy=False;self.searchbtn.configure(state='normal',text='Search')
                        for w in self.action_buttons:w.configure(state='normal')
                    elif k=='log':
                        self.logs.configure(state='normal');self.logs.insert('end','\n'+str(v)[:500]);self.logs.see('end');self.logs.configure(state='disabled');self.status.set(str(v)[:160])
            except queue.Empty:pass
            self.win.after(100,self.poll)
        def close(self):
            if not self.busy:self.persist()
            super().close()
    return Desktop
