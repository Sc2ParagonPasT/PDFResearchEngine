"""v0.4 desktop usability layer; all native security decisions remain in Pipeline."""
import dataclasses
import datetime as dt
import os
import queue
import re
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from pathlib import Path
from desktop_helpers import safe_pdf_name, export_folder, load_preferences, save_preferences
from discovery_v03 import Network
from security import Pipeline, Blocked

BG='#11151b'; PANEL='#1b222c'; FG='#e5eaf2'; MUTED='#a3b0c2'
ACTIVE='Screened / OCR indexed'
DEFAULT_TEXT_SIZE=14
MIN_TEXT_SIZE=10
MAX_TEXT_SIZE=24
WHEEL_TAG='PDFResearchWheel'

def font_size(value):
    try:return max(MIN_TEXT_SIZE,min(MAX_TEXT_SIZE,round(float(value))))
    except (TypeError,ValueError,OverflowError):return DEFAULT_TEXT_SIZE

def plain_stage(message):
    text=str(message)
    labels={
        'Checking definition freshness and retrieving into quarantine':'Checking virus definitions and downloading the document for inspection',
        'Download completed; checking staged bytes':'Download complete; checking document integrity',
        'Checking staged PDF header, end marker and hash':'Checking document integrity',
        'ClamAV scanning staged PDF':'Virus scanning',
        'ClamAV scan completed; starting YARA':'Virus scan complete; checking for suspicious content',
        'YARA scan completed without policy matches':'Suspicious-content check complete',
        'Checking original PDF structure':'Checking document safety',
        'Original structure check passed':'Document structure check passed',
        'Checking reconstructed PDF structure and OCR text':'Checking rebuilt document and searchable text',
        'ClamAV scanning reconstructed PDF':'Final virus scan',
        'Reconstructed ClamAV scan completed; starting YARA':'Final virus scan complete; checking for suspicious content again',
        'Reconstructed YARA scan completed without policy matches':'Final suspicious-content check complete',
        'Validating worker evidence against exact input and reconstructed bytes':'Verifying all security checks and document integrity',
        'Validated inspection evidence; indexing searchable derivative':'Adding the checked document to your library',
        'Final rescan before automatic export':'Repeating security checks before saving your PDF',
    }
    if text in labels:return labels[text]
    m=re.fullmatch(r'Rasterization and OCR: page (\d+) of (\d+)',text)
    if m:return 'Rebuilding document and making text searchable: page '+m[1]+' of '+m[2]
    if text.startswith('Final security rescan: '):return 'Repeating security checks before saving: '+text.split(': ',1)[1]
    return text

def wheel_steps(event):
    if getattr(event,'num',None)==4:return 1
    if getattr(event,'num',None)==5:return -1
    delta=getattr(event,'delta',0) or 0
    return (1 if delta>0 else -1)*max(1,min(10,abs(int(delta))//120)) if delta else 0

def route_scroll(widget,steps,horizontal=False):
    """Scroll the innermost available view, then its containing scroll area at an edge."""
    axis='x' if horizontal else 'y'
    while widget is not None:
        if isinstance(widget,(tk.Text,tk.Listbox,tk.Canvas,ttk.Treeview)):
            try:
                view=getattr(widget,axis+'view');first,last=view()
                if (steps>0 and first>0.000001) or (steps<0 and last<0.999999):
                    getattr(widget,axis+'view_scroll')(-steps,'units')
                    return True
            except (tk.TclError,AttributeError,ValueError):pass
        widget=getattr(widget,'master',None)
    return False

def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)

def scroll_shell(parent):
    outer=ttk.Frame(parent);outer.pack(fill='both',expand=True)
    canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
    canvas.grid(row=0,column=0,sticky='nsew');outer.rowconfigure(0,weight=1);outer.columnconfigure(0,weight=1)
    y=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview);y.grid(row=0,column=1,sticky='ns')
    x=ttk.Scrollbar(outer,orient='horizontal',command=canvas.xview);x.grid(row=1,column=0,sticky='ew')
    canvas.configure(xscrollcommand=x.set,yscrollcommand=y.set)
    inner=ttk.Frame(canvas);window=canvas.create_window(0,0,window=inner,anchor='nw')
    scheduled=[False]
    def fit():
        scheduled[0]=False
        if not canvas.winfo_exists():return
        width=max(canvas.winfo_width(),inner.winfo_reqwidth());height=max(canvas.winfo_height(),inner.winfo_reqheight())
        canvas.itemconfigure(window,width=width,height=height);canvas.configure(scrollregion=(0,0,width,height))
    def update(*_):
        if not scheduled[0]:scheduled[0]=True;canvas.after_idle(fit)
    inner.bind('<Configure>',update);canvas.bind('<Configure>',update)
    return inner,update

def reveal(folder):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError('Folder is unavailable: '+str(folder))
    if os.name=='nt':os.startfile(str(folder))
    else:subprocess.Popen(['xdg-open',str(folder)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

class Monitor:
    def __init__(self,app):
        self.app=app;self.win=tk.Toplevel(app.win);self.win.title('Processing Monitor')
        self.win.configure(bg=BG);self.win.geometry('880x650');self.win.minsize(540,420)
        self.win.protocol('WM_DELETE_WINDOW',self.hide)
        self.timer=None;self.records=[];self.last_head='';self.finished=False
        content,self.update_scroll=scroll_shell(self.win)
        box=ttk.Frame(content,padding=14);box.pack(fill='both',expand=True)
        self.head=tk.StringVar();self.summary=tk.StringVar()
        ttk.Label(box,textvariable=self.head,wraplength=760).pack(fill='x',pady=5)
        ttk.Label(box,textvariable=self.summary,wraplength=760).pack(fill='x',pady=4)
        self.bar=ttk.Progressbar(box,mode='determinate');self.bar.pack(fill='x',pady=5)
        tableframe=ttk.Frame(box);tableframe.pack(fill='both',expand=True,pady=5)
        self.table=ttk.Treeview(tableframe,columns=('title','outcome'),show='headings',height=7)
        for key,title,width in [('title','Document',470),('outcome','Outcome',240)]:
            self.table.heading(key,text=title);self.table.column(key,width=width,minwidth=100)
        self.table.pack(side='left',fill='both',expand=True)
        tablebar=ttk.Scrollbar(tableframe,command=self.table.yview);tablebar.pack(side='right',fill='y');self.table.configure(yscrollcommand=tablebar.set)
        logframe=ttk.Frame(box);logframe.pack(fill='both',expand=True)
        self.log=app.text(logframe,8);self.log.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(logframe,command=self.log.yview);sb.pack(side='right',fill='y');self.log.configure(yscrollcommand=sb.set,state='disabled')
        controls=ttk.Frame(box);controls.pack(fill='x',pady=8)
        self.cancel=ttk.Button(controls,text='Cancel remaining',command=app.stop.set,state='disabled');self.cancel.pack(side='left')
        ttk.Button(controls,text='Open export folder',command=app.open_export).pack(side='left',padx=6)
        ttk.Button(controls,text='Close / hide',command=self.hide).pack(side='right')
        options=ttk.Frame(box);options.pack(fill='x',pady=4)
        self.auto_close=tk.BooleanVar(value=bool(app.prefs.get('monitor_auto_close',True)))
        ttk.Checkbutton(options,text='Close 5 seconds after success',variable=self.auto_close,command=self.change_auto_close).pack(anchor='w')
        self.advanced=tk.BooleanVar(value=False)
        ttk.Checkbutton(options,text='Advanced details',variable=self.advanced,command=self.refresh_log).pack(anchor='w')
        self.countdown=tk.StringVar(value='')
        ttk.Label(options,textvariable=self.countdown,wraplength=720).pack(anchor='w')
        self.rows=[];self.states=[]
        app.install_wheel_tags(self.win)
        self.win.bind('<Configure>',lambda e:self._wrap(e))
    def _wrap(self,e):
        if e.widget==self.win:
            for w in walk(self.win):
                if isinstance(w,ttk.Label):w.configure(wraplength=max(260,e.width-45))
    def begin(self,titles):
        self.cancel_countdown();self.finished=False;self.records.clear();self.last_head=''
        self.table.delete(*self.table.get_children());self.rows=[];self.states=['Queued']*len(titles)
        for title in titles:self.rows.append(self.table.insert('','end',values=(title,'Queued')))
        self.bar.configure(maximum=max(1,len(titles)),value=0);self.set_head('Preparing mandatory security checks')
        self.log.configure(state='normal');self.log.delete('1.0','end');self.log.configure(state='disabled')
        self.cancel.configure(state='normal');self.counts();self.show()
    def cancel_countdown(self):
        if self.timer is not None:self.win.after_cancel(self.timer);self.timer=None
        self.countdown.set('')
    def hide(self):
        self.cancel_countdown();self.win.withdraw()
    def show(self):
        self.cancel_countdown();self.win.deiconify();self.win.lift()
    def change_auto_close(self):
        self.app.prefs['monitor_auto_close']=self.auto_close.get();self.app.persist()
        if not self.auto_close.get():self.cancel_countdown()
    def tick(self,seconds):
        self.timer=None
        if not self.auto_close.get() or not self.finished or not self.states or any(s!='Completed' for s in self.states):self.cancel_countdown();return
        if seconds<=0:self.hide();return
        self.countdown.set(f'All documents completed. Closing in {seconds} second(s). Uncheck auto-close to keep this report open.')
        self.timer=self.win.after(1000,lambda:self.tick(seconds-1))
    def set_head(self,msg):
        self.last_head=str(msg)[:500]
        self.head.set(self.last_head if self.advanced.get() else plain_stage(self.last_head))
    def refresh_log(self):
        self.set_head(self.last_head)
        self.log.configure(state='normal');self.log.delete('1.0','end')
        for stamp,msg in self.records:self.log.insert('end',stamp+'  '+(msg if self.advanced.get() else plain_stage(msg))+'\n')
        self.log.see('end');self.log.configure(state='disabled')
    def counts(self):
        counts={s:self.states.count(s) for s in ('Completed','Active','Blocked','Failed','Cancelled','Queued')}
        self.summary.set(' | '.join(f'{k}: {v}' for k,v in counts.items()))
        self.bar.configure(value=sum(counts[x] for x in ('Completed','Blocked','Failed','Cancelled')))
    def event(self,kind,value):
        if kind=='batch_row':
            i,state,detail=value
            self.states[i]=state;self.table.set(self.rows[i],'outcome',state);self.table.see(self.rows[i])
            self.set_head(f'Document {i+1} of {len(self.rows)}: '+plain_stage(detail));self.counts();self.append(detail)
        elif kind=='batch_log':self.set_head(value);self.append(value)
        elif kind=='batch_end':
            for i,s in enumerate(self.states):
                if s in ('Queued','Active'):
                    outcome='Cancelled' if value and s=='Queued' else 'Failed'
                    self.states[i]=outcome;self.table.set(self.rows[i],'outcome',outcome)
            self.finished=True;self.counts();self.cancel.configure(state='disabled')
            success=bool(self.states) and all(s=='Completed' for s in self.states) and not value
            self.set_head('All documents completed successfully.' if success else 'Processing finished. Review the document outcomes.')
            self.append(self.last_head)
            self.cancel_countdown()
            if success and self.auto_close.get() and self.win.state()!='withdrawn':self.tick(5)
            elif not success:self.show()
    def append(self,msg):
        stamp=dt.datetime.now().strftime('%H:%M:%S');raw=str(msg)[:500];self.records.append((stamp,raw))
        self.log.configure(state='normal');self.log.insert('end',stamp+'  '+(raw if self.advanced.get() else plain_stage(raw))+'\n');self.log.see('end');self.log.configure(state='disabled')

def desktop_class(Base):
    class Desktop(Base):
        def style(self):
            super().style()
            self.prefpath=self.root/'desktop-v04.json';self.prefs=load_preferences(self.prefpath)
            size=font_size(self.prefs.get('text_size',DEFAULT_TEXT_SIZE))
            self.normalfont=font.Font(self.win,family='Segoe UI',size=size)
            self.titlefont=font.Font(self.win,family='Segoe UI',size=size+7,weight='bold')
            self.textsize=tk.IntVar(value=size)
            self.scalevalue=tk.DoubleVar(value=size)
            self.size_label=tk.StringVar(value=f'{size} pt')
            self.sizeset=None;self.monitor=None
            self.apply_fonts()
        def apply_fonts(self,*_):
            size=int(self.textsize.get())
            self.normalfont.configure(size=size);self.titlefont.configure(size=size+7)
            self.size_label.set(f'{size} pt')
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
            if hasattr(self,'update_scroll'):self.update_scroll()
            if self.monitor is not None:self.monitor.update_scroll()
            if hasattr(self,'minus'):self.minus.configure(state='disabled' if size<=MIN_TEXT_SIZE else 'normal');self.plus.configure(state='disabled' if size>=MAX_TEXT_SIZE else 'normal')
            self.prefs['text_size']=size
            if self.sizeset is not None:self.win.after_cancel(self.sizeset)
            self.sizeset=self.win.after(350,self.persist)
        def persist(self):
            if self.sizeset is not None:self.win.after_cancel(self.sizeset);self.sizeset=None
            try:save_preferences(self.prefpath,self.prefs)
            except OSError as e:self.status.set('Could not save preferences: '+str(e)) if hasattr(self,'status') else None
        def text(self,parent,height=6):
            w=super().text(parent,height);w.configure(font=self.normalfont);return w
        def layout(self):
            self.content_parent,self.update_scroll=scroll_shell(self.win)
            super().layout()
            self.win.title('PDF Research Engine | v0.4.1 Experimental')
            self.win.geometry(f'{min(1320,int(self.win.winfo_screenwidth()*.92))}x{min(900,int(self.win.winfo_screenheight()*.85))}')
            shell=self.content_parent.winfo_children()[0]
            header=ttk.Frame(self.win,padding=(8,4));header.pack(fill='x',before=self.content_parent.master.master)
            sizebar=ttk.Frame(header);sizebar.pack(side='right')
            ttk.Label(sizebar,text='Text size').pack(side='left',padx=(0,6))
            self.minus=ttk.Button(sizebar,text='−',width=3,command=lambda:self.resize_text(self.textsize.get()-1));self.minus.pack(side='left')
            self.scale=ttk.Scale(sizebar,from_=MIN_TEXT_SIZE,to=MAX_TEXT_SIZE,variable=self.scalevalue,length=112,command=self.resize_text)
            self.scale.pack(side='left',padx=5)
            self.plus=ttk.Button(sizebar,text='+',width=3,command=lambda:self.resize_text(self.textsize.get()+1));self.plus.pack(side='left')
            ttk.Label(sizebar,textvariable=self.size_label,width=6,anchor='center').pack(side='left',padx=3)
            ttk.Button(sizebar,text='Reset',command=lambda:self.resize_text(DEFAULT_TEXT_SIZE)).pack(side='left')
            helpbar=ttk.Frame(shell);helpbar.pack(fill='x',before=shell.winfo_children()[0],pady=(0,8))
            ttk.Button(helpbar,text='Quick Start Guide',command=self.welcome).pack(side='left')
            ttk.Button(helpbar,text='Processing Monitor',command=self.show_monitor).pack(side='left',padx=5)
            ttk.Button(helpbar,text='About / Notices',command=self.about).pack(side='left')
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
            ttk.Checkbutton(libbar,text='Automatically export after final rescan',variable=self.autoexport,command=self.store_auto).grid(row=2,column=0,columnspan=3,sticky='w',pady=3)
            self.pathlabel=tk.StringVar()
            ttk.Label(libbar,textvariable=self.pathlabel,wraplength=1100).grid(row=3,column=0,columnspan=3,sticky='w')
            self.update_paths()
            self.action_buttons=[]
            for w in walk(self.win):
                if isinstance(w,ttk.Button) and w.cget('text') in ('Inspect & index selected','Recheck PDF access','Rescan & export PDF','Recheck library','Check security','Update definitions'):
                    self.action_buttons.append(w)
            self.apply_fonts()
            self.bind_wheel()
            if not self.prefs.get('hide_welcome',False):self.win.after(350,lambda:None if self.prefs.get('hide_welcome',False) else self.welcome())
        def install_wheel_tags(self,widget):
            for w in [widget,*walk(widget)]:
                tags=w.bindtags()
                if WHEEL_TAG not in tags:w.bindtags((WHEEL_TAG,*tags))
        def bind_wheel(self):
            for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
                self.win.bind_class(WHEEL_TAG,sequence,self.on_wheel)
            self.win.bind_class(WHEEL_TAG,'<Control-Key-0>',self.reset_text)
            self.win.bind_class(WHEEL_TAG,'<Control-KP_0>',self.reset_text)
            self.win.bind_all('<Map>',lambda e:self.install_wheel_tags(e.widget) if isinstance(e.widget,tk.Misc) else None,add='+')
            self.install_wheel_tags(self.win)
        def reset_text(self,event=None):
            self.resize_text(DEFAULT_TEXT_SIZE);return 'break'
        def on_wheel(self,event):
            steps=wheel_steps(event)
            if not steps:return
            if event.state & 0x0004:
                self.resize_text(self.textsize.get()+steps);return 'break'
            route_scroll(event.widget,steps,bool(event.state & 0x0001))
            return 'break'
        def resize_text(self,v):
            size=font_size(v)
            if self.textsize.get()!=size:
                self.textsize.set(size);self.apply_fonts()
            if abs(self.scalevalue.get()-size)>0.0001:self.scalevalue.set(size)
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
        def about(self):
            import sys
            w=tk.Toplevel(self.win);w.title('About PDF Research Engine');w.geometry('850x650');w.configure(bg=BG)
            f=ttk.Frame(w,padding=12);f.pack(fill='both',expand=True)
            ttk.Label(f,text='PDF Research Engine v0.4.1 • Experimental',style='Title.TLabel').pack(anchor='w')
            body=self.text(f,15);body.pack(fill='both',expand=True,pady=8)
            base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
            p=base/'THIRD_PARTY_NOTICES.md'
            text='Free, open-source research application. Unsigned experimental build. Security screening reduces risk but does not guarantee safety; the worker is not an OS sandbox.\n\nSource: https://github.com/Sc2ParagonPasT/PDFResearchEngine\n\n'
            try:text+=p.read_text(encoding='utf-8')
            except OSError:text+='Third-party notices are available in the source repository.'
            body.insert('1.0',text);body.configure(state='disabled')
            ttk.Button(f,text='Close',command=w.destroy).pack(anchor='e');self.install_wheel_tags(w)
        def welcome(self):
            if getattr(self,'guide',None) and self.guide.winfo_exists():self.guide.lift();return
            w=self.guide=tk.Toplevel(self.win);w.title('Welcome to PDF Research Engine');w.geometry('780x650');w.configure(bg=BG)
            f=ttk.Frame(w,padding=18);f.pack(fill='both',expand=True)
            ttk.Label(f,text='Start researching',style='Title.TLabel').pack(anchor='w')
            reading=ttk.Frame(f);reading.pack(fill='both',expand=True,pady=10)
            body=self.text(reading,12);body.pack(side='left',fill='both',expand=True)
            scroll=ttk.Scrollbar(reading,command=body.yview);scroll.pack(side='right',fill='y');body.configure(yscrollcommand=scroll.set)
            body.insert('1.0','SEARCH\nType a topic and press Enter or click Search. The app checks candidate PDF links before showing them.\n\nINSPECT\nSelect one or more results and choose Inspect & index selected. Watch the Processing Monitor for downloading, virus scanning, document safety checks and making text searchable. Blocked files are not released.\n\nLIBRARY\nOpen Local library to find searchable text and processed documents. Open Library Folder shows internal .screened files.\n\nSAVE\nUse Rescan & export PDF to save a normal PDF using the publication title. Choose an export folder and optionally enable automatic export.\n\nCUSTOMIZE\nUse the + and − buttons or the slider to change text size. Scroll with the mouse wheel; hold Ctrl while scrolling to resize the text. Ctrl + 0 resets the size to 14 pt. The Processing Monitor closes automatically after successful batches unless you turn that option off. Security screening reduces risk but cannot guarantee that documents are harmless. This experimental application is not an OS sandbox.')
            body.configure(state='disabled')
            hide=tk.BooleanVar(value=bool(self.prefs.get('hide_welcome',False)))
            ttk.Checkbutton(f,text="Don't show this again",variable=hide).pack(anchor='w')
            def done():
                self.prefs['hide_welcome']=hide.get();self.persist();w.destroy()
            buttons=ttk.Frame(f);buttons.pack(fill='x',pady=8)
            ttk.Button(buttons,text='Start Researching',command=done).pack(side='right')
            w.protocol('WM_DELETE_WINDOW',done);w.bind('<Escape>',lambda e:done());self.install_wheel_tags(w)
        def show_monitor(self):
            if self.monitor is None:self.monitor=Monitor(self)
            self.monitor.show()
        def batch(self,titles,fn):
            if self.busy:messagebox.showinfo('Busy','Stop or finish the current operation first.');return
            self.show_monitor();self.monitor.begin(titles)
            def work():
                try:fn()
                finally:self.events.put(('batch_end',self.stop.is_set()))
            self.start(work)
        def start(self,fn):
            ok=super().start(fn)
            if ok:
                self.searchbtn.configure(text='Working…')
                for w in self.action_buttons:w.configure(state='disabled')
            return ok
        def search(self):
            if self.busy:messagebox.showinfo('Busy','Wait for the current operation or click Stop.');return
            super().search()
            if self.busy:self.searchbtn.configure(text='Searching…');self.searchprogress.set('Searching and verifying PDF candidates…')
        def selected_action(self,action):
            if self.busy:messagebox.showinfo('Busy','Stop or finish the current search first.');return
            ids=self.tree.selection()
            if not ids:messagebox.showinfo('Select documents','Select one or more results first.');return
            if action!='download':return super().selected_action(action)
            if len(ids)>30:messagebox.showinfo('Batch limit','Select up to 30 documents.');return
            if not messagebox.askyesno('Secure inspection',f'Inspect {len(ids)} selected document(s)? Each original and reconstructed copy must pass mandatory security checks. Only passing searchable derivatives are indexed. The worker is not an OS sandbox.'):return
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
                            outcome='Completed';detail=r.title+' — added to your library'
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
            finally:self.win.after(100,self.poll)
        def close(self):
            if not self.busy:self.persist()
            super().close()
    return Desktop
