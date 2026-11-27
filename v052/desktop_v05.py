"""v0.5 repository UI, preserving the v0.4.1 desktop and its settings."""
import tkinter as tk
from tkinter import ttk,messagebox
import sqlite3
from desktop_v04 import desktop_class,scroll_shell,walk
from desktop_helpers import save_preferences
from repositories_v05 import SOURCES,BY_KEY,LIMITS,DEFAULT_LIMIT,normalize_limit,MetadataIndex,run_search,Network
from discovery_v03 import DEFAULT_PROVIDERS
from context_v052 import MODES,mode_name,query_terms,clauses,Policy
def repository_desktop(Base):
    class Desktop(desktop_class(Base)):
        def layout(self):
            super().layout()
            saved=self.prefs.get('repositories_v05',list(DEFAULT_PROVIDERS))
            if not isinstance(saved,list):saved=list(DEFAULT_PROVIDERS)
            self.selected_sources={k for k in saved if isinstance(k,str) and k in BY_KEY}
            for w in walk(self.discovery):
                if isinstance(w,ttk.Checkbutton) and w.cget('text') in self.providers:w.grid_remove()
            for p,v in self.providers.items():v.set(p in self.selected_sources)
            bar=ttk.Frame(self.discovery);bar.pack(fill='x',before=self.searchbtn.master,pady=5)
            self.source_summary=tk.StringVar(value=f'{len(self.selected_sources)} selected')
            ttk.Button(bar,text='Choose research repositories',command=self.repository_window).pack(side='left')
            ttk.Label(bar,textvariable=self.source_summary).pack(side='left',padx=8)
            ttk.Label(bar,text='Max results').pack(side='left',padx=(8,4))
            self.result_limit=tk.StringVar(value=str(normalize_limit(self.prefs.get('result_limit',DEFAULT_LIMIT))))
            c=ttk.Combobox(bar,textvariable=self.result_limit,values=[str(x) for x in LIMITS],width=7,state='readonly');c.pack(side='left')
            c.bind('<<ComboboxSelected>>',lambda e:self.save_limit())
            self.repo_window=None
            self.depth.set(mode_name(self.prefs.get('relevance_mode','Balanced')))
            for widget in walk(self.discovery):
                if isinstance(widget,ttk.Combobox) and str(widget.cget('textvariable'))==str(self.depth):
                    widget.configure(values=MODES)
                    widget.bind('<<ComboboxSelected>>',lambda e:self.generate())
            self.generate()
            filters=ttk.LabelFrame(self.discovery,text='Optional search filters',padding=6)
            filters.pack(fill='x',before=self.searchbtn.master,pady=4)
            self.required_terms=tk.StringVar();self.excluded_terms=tk.StringVar()
            for i,(label,var) in enumerate((('Require',self.required_terms),('Exclude',self.excluded_terms))):
                ttk.Label(filters,text=label).grid(row=i,column=0,sticky='w',padx=4,pady=2)
                ttk.Entry(filters,textvariable=var).grid(row=i,column=1,sticky='ew',padx=4,pady=2)
            filters.columnconfigure(1,weight=1)
            ttk.Label(filters,text='Separate entries with commas. Multi-word entries match as phrases.',wraplength=900).grid(row=2,column=0,columnspan=2,sticky='w')
            self.tree.configure(columns=(*self.tree.cget('columns'),'relevance','reason'))
            self.tree.heading('relevance',text='Match / 100',command=self.sort_matches);self.tree.column('relevance',width=125,minwidth=85,stretch=False)
            self.tree.heading('reason',text='Why it matched');self.tree.column('reason',width=320,minwidth=120)
            self.tree.configure(displaycolumns=('title','relevance','source','year','status','query','reason'))
            self.match_details=tk.StringVar(value='Select a result to see why it matched.')
            ttk.Label(self.discovery,textvariable=self.match_details,wraplength=1000).pack(fill='x',after=self.tree.master,pady=3)
            ttk.Button(self.searchbtn.master,text='Other copies',command=self.show_copies).pack(side='left',padx=5)
            self.apply_fonts();self.install_wheel_tags(self.win)
        def generate(self):
            self.terms=query_terms(self.q.get(),self.depth.get())
            self.termtext.delete('1.0','end');self.termtext.insert('1.0','\n'.join(self.terms))
            self.generated_query=self.q.get();self.generated_depth=self.depth.get()
        def row(self,r):
            return (*super().row(r),str(getattr(r,'relevance','')),getattr(r,'match_reason',''))
        def selection(self,event=None):
            super().selection(event)
            if not hasattr(self,'match_details'):return
            ids=self.tree.selection();r=self.results.get(ids[0]) if ids else None
            self.match_details.set((getattr(r,'match_reason','')+f' | {len(getattr(r,"alternatives",()))} other verified location(s)') if r else 'Select a result to see why it matched.')
        def sort_matches(self):
            for n,i in enumerate(sorted(self.tree.get_children(),key=lambda x:-getattr(self.results.get(x),'relevance',0))):self.tree.move(i,'',n)
        def show_copies(self):
            ids=self.tree.selection();r=self.results.get(ids[0]) if ids else None
            if self.busy:return
            copies=getattr(r,'alternatives',())
            if not copies:messagebox.showinfo('Other copies','No other likely copies found for the selected document.',parent=self.win);return
            import dataclasses
            from engine import checked_url
            w=tk.Toplevel(self.win);w.title('Other verified locations');w.geometry('800x420')
            frame=ttk.Frame(w,padding=12);frame.pack(fill='both',expand=True)
            ttk.Label(frame,text='Likely copies based on metadata, not byte-identical proof.',wraplength=720).pack(fill='x')
            table=ttk.Treeview(frame,columns=('source','url'),show='headings',selectmode='browse')
            table.heading('source',text='Repository');table.heading('url',text='Verified location')
            table.column('source',width=160);table.column('url',width=550);table.pack(fill='both',expand=True,pady=8)
            locations=((r.source,r.url),*copies)
            for n,(source,url) in enumerate(locations):table.insert('','end',iid=str(n),values=(source,url))
            def choose():
                if self.busy or self.results.get(ids[0]) is not r:return
                selected=table.selection()
                if not selected:return
                source,url=locations[int(selected[0])]
                try:checked_url(url,set(self.hosts))
                except ValueError as e:messagebox.showerror('Location unavailable',str(e),parent=w);return
                replacement=dataclasses.replace(r,source=source,url=url,alternatives=tuple(x for x in locations if x!=(source,url)),digest='')
                self.results[ids[0]]=replacement;self.tree.item(ids[0],values=self.row(replacement));self.selection();w.destroy()
            ttk.Button(frame,text='Use selected location',command=choose).pack(anchor='e')
            self.install_wheel_tags(w)
        def save_limit(self):
            self.prefs['result_limit']=normalize_limit(self.result_limit.get());self.persist()
        def repository_window(self):
            if self.busy:messagebox.showinfo('Busy','Finish or stop the current operation first.',parent=self.win);return
            if self.repo_window is not None and self.repo_window.winfo_exists():self.repo_window.lift();return
            w=self.repo_window=tk.Toplevel(self.win);w.title('Choose research repositories')
            w.geometry(f'{min(950,int(w.winfo_screenwidth()*.88))}x{min(700,int(w.winfo_screenheight()*.82))}')
            outer=ttk.Frame(w,padding=12);outer.pack(fill='both',expand=True)
            ttk.Label(outer,text='Research repositories',style='Title.TLabel').pack(anchor='w')
            ttk.Label(outer,text='Select collections by category. New domains require explicit approval.',wraplength=740).pack(fill='x',pady=6)
            control=ttk.Frame(outer);control.pack(fill='x')
            choice={s.key:tk.BooleanVar(value=s.key in self.selected_sources) for s in SOURCES}
            self.repository_choices=choice
            count=tk.StringVar()
            def refresh(*_):count.set(f'{sum(v.get() for v in choice.values())} repositories selected')
            def select(keys,value):
                for k in keys:choice[k].set(value)
                refresh()
            ttk.Button(control,text='Select all',command=lambda:select(choice,True)).pack(side='left')
            ttk.Button(control,text='Clear all',command=lambda:select(choice,False)).pack(side='left',padx=5)
            ttk.Label(control,textvariable=count).pack(side='right')
            footer=ttk.Frame(outer);footer.pack(side='bottom',fill='x',pady=5)
            inner,fit=scroll_shell(outer)
            for category in sorted({s.category for s in SOURCES}):
                group=[s for s in SOURCES if s.category==category];keys=[s.key for s in group]
                frame=ttk.LabelFrame(inner,text=category,padding=8);frame.pack(fill='x',pady=4,padx=4)
                ttk.Button(frame,text='Toggle category',command=lambda ks=keys:select(ks,not all(choice[k].get() for k in ks))).pack(anchor='e')
                for s in group:
                    status=s.status if set(s.hosts)<=set(self.hosts) else 'Domain approval needed'
                    ttk.Checkbutton(frame,text=s.name+'  ('+status+')',variable=choice[s.key],command=refresh).pack(anchor='w')
            def apply():
                if self.busy:messagebox.showinfo('Busy','Finish or stop the current operation first.',parent=w);return
                keys={k for k,v in choice.items() if v.get()}
                missing=sorted({h for k in keys for h in BY_KEY[k].hosts}-set(self.hosts))
                if missing:
                    if not messagebox.askyesno('Approve repository domains','Allow HTTPS access to these exact domains?\n\n'+'\n'.join(missing)+'\n\nAll document security checks remain mandatory.',parent=w):return
                    new=sorted(set(self.hosts)|set(missing))
                    try:save_preferences(self.config,{'hosts':new,'seeds':self.seeds,'threat_action':self.threat_action,'auto_rescan':self.auto_rescan})
                    except OSError as e:messagebox.showerror('Could not save domain approvals',str(e),parent=w);return
                    self.hosts=new;self.hosttext.delete('1.0','end');self.hosttext.insert('1.0','\n'.join(new))
                self.selected_sources=keys
                for p,v in self.providers.items():v.set(p in keys)
                self.prefs['repositories_v05']=sorted(keys);self.persist()
                self.source_summary.set(f'{len(keys)} selected');w.destroy()
            ttk.Button(footer,text='Cancel',command=w.destroy).pack(side='right')
            ttk.Button(footer,text='Apply selection',style='Accent.TButton',command=apply).pack(side='right',padx=5)
            refresh();self.install_wheel_tags(w)
        def search(self):
            if self.busy:messagebox.showinfo('Busy','Wait for the current operation or click Stop.',parent=self.win);return
            if self.generated_query!=self.q.get() or self.generated_depth!=self.depth.get():self.generate()
            terms=list(dict.fromkeys(x.strip()[:240] for x in self.termtext.get('1.0','end').splitlines() if x.strip()))[:24]
            keys=[s.key for s in SOURCES if s.key in self.selected_sources];seeds=list(self.seeds) if self.crawlvar.get() else []
            if not terms or not (keys or seeds):messagebox.showinfo('Search','Enter a topic and choose at least one repository.',parent=self.win);return
            if any(not set(BY_KEY[k].hosts)<=set(self.hosts) for k in keys):
                messagebox.showinfo('Domain approval needed','Open Choose research repositories and apply your selection to approve missing domains.',parent=self.win);return
            self.prefs['relevance_mode']=mode_name(self.depth.get());self.save_limit();limit=normalize_limit(self.result_limit.get())
            policy=Policy(self.q.get(),mode_name(self.depth.get()),clauses(self.required_terms.get()),clauses(self.excluded_terms.get()))
            if not policy.query.strip():messagebox.showinfo('Search','Enter the original research topic first.',parent=self.win);return
            self.tree.delete(*self.tree.get_children());self.results.clear()
            self.status.set('Searching approved repositories…');self.searchprogress.set('Searching and verifying PDF candidates…')
            net=Network(self.hosts)
            def work():
                emit=lambda k,v:self.events.put((k,v))
                try:index=MetadataIndex(self.root/'repository-metadata-v05.sqlite3')
                except (OSError,sqlite3.Error) as e:index=None;emit('log','Metadata cache unavailable: '+str(e))
                run_search(net,keys,terms,seeds,self.stop,emit,index,limit,policy)
            if self.start(work):self.searchbtn.configure(text='Searching…')
    return Desktop
