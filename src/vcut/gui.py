from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .audit_log import append_event
from .edl_service import EDLService
from .exceptions import VCutError
from .media_probe import dependency_status, probe_media
from .models import CameraSource, EDLSegment, ProgrammeSegment, Project, SubtitleEntry, SynchronizationConfig, edl_from_dict, subtitle_from_dict, to_dict
from .programme_reader import read_programme
from .project_service import ProjectService, atomic_write_json
from .renderer import Renderer
from .subtitle_service import import_srt, overlap_warnings
from .synchronization import SynchronizationService
from .timecode import format_timecode, parse_timecode
from .ui.theme import COLORS, FONTS, apply_theme
from .validation import ValidationService, blocking


class VCutApp(tk.Tk):
    STEPS = ("Project", "Cameras", "Synchronize", "Segments", "EDL review", "Audio & text", "Export")

    def __init__(self) -> None:
        super().__init__()
        self.title("VCut — Multi-Camera Video Assistant")
        self.minsize(1280, 720)
        width = min(1440, int(self.winfo_screenwidth() * .9)); height = min(900, int(self.winfo_screenheight() * .9))
        self.geometry(f"{width}x{height}+{max(0, (self.winfo_screenwidth()-width)//2)}+{max(0, (self.winfo_screenheight()-height)//2)}")
        apply_theme(self)
        self.service = ProjectService(); self.edl_service = EDLService(); self.validation = ValidationService()
        self.project_root: Path | None = None; self.project: Project | None = None
        self.cameras: list[CameraSource] = []; self.programme: list[ProgrammeSegment] = []
        self.synchronization: SynchronizationConfig | None = None; self.segments: list[EDLSegment] = []; self.subtitles: list[SubtitleEntry] = []
        self.current_step = 0; self.pages: list[ttk.Frame] = []; self.nav_buttons: list[tk.Button] = []
        self.status_var = tk.StringVar(value="Local processing only — no footage is uploaded.")
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.bind("<Control-n>", lambda _e: self.create_project()); self.bind("<Control-o>", lambda _e: self.open_project()); self.bind("<Control-s>", lambda _e: self.save_all())
        self._show_home()

    def _clear(self) -> None:
        for child in self.winfo_children(): child.destroy()

    def _show_home(self) -> None:
        self._clear()
        frame = ttk.Frame(self, padding=48); frame.pack(fill="both", expand=True)
        card = ttk.Frame(frame, style="Panel.TFrame", padding=36); card.place(relx=.5, rely=.45, anchor="center", width=700)
        ttk.Label(card, text="VCut", font=("Segoe UI", 34, "bold"), foreground=COLORS["purple"], style="Panel.TLabel").pack(anchor="w")
        ttk.Label(card, text="Multi-Camera Video Assistant", font=FONTS["section"], style="Panel.TLabel").pack(anchor="w", pady=(0, 18))
        ttk.Label(card, text="Plan, review, approve, and render a graduation video while keeping footage on this computer.", wraplength=610, style="Panel.TLabel").pack(anchor="w", pady=(0, 24))
        actions = ttk.Frame(card, style="Panel.TFrame"); actions.pack(fill="x")
        ttk.Button(actions, text="Create project", style="Primary.TButton", command=self.create_project).pack(side="left")
        ttk.Button(actions, text="Open project", command=self.open_project).pack(side="left", padx=10)
        status = dependency_status(); media = "FFmpeg ready" if status["ffmpeg"] and status["ffprobe"] else "FFmpeg not found — planning works; media inspection/rendering needs installation"
        ttk.Label(card, text="● Local processing   •   " + media, foreground=COLORS["success"] if status["ffmpeg"] else COLORS["warning"], wraplength=610, style="Panel.TLabel").pack(anchor="w", pady=(26, 0))

    def create_project(self) -> None:
        folder = filedialog.askdirectory(title="Choose an empty folder for the VCut project")
        if not folder: return
        name = simpledialog.askstring("Project name", "Project name:", initialvalue="Graduation 2026", parent=self)
        if not name: return
        authorized = messagebox.askyesno("Footage authorization", "Is the footage simulated or appropriately authorized for local processing?", parent=self)
        try:
            root = self.service.create_project(Path(folder), Project(name, consent_confirmed=authorized))
            self._load(root); append_event(root, "project_created")
        except VCutError as exc: self._error(exc)

    def open_project(self) -> None:
        folder = filedialog.askdirectory(title="Open a VCut project")
        if folder:
            try: self._load(Path(folder)); append_event(Path(folder), "project_opened")
            except VCutError as exc: self._error(exc)

    def _load(self, root: Path) -> None:
        self.project_root = root.resolve(); self.project = self.service.load_project(root); self.cameras = self.service.load_cameras(root)
        self.programme = self._load_items("programme.json", ProgrammeSegment); self.segments = self._load_items("edl.json", edl_from_dict, key="segments")
        self.subtitles = self._load_items("subtitles.json", subtitle_from_dict)
        sync_path = root / "synchronization.json"
        self.synchronization = SynchronizationConfig(**json.loads(sync_path.read_text(encoding="utf-8"))) if sync_path.exists() else None
        self._build_shell(); self.show_step(0)

    def _load_items(self, filename, constructor, key=None):
        path = self.project_root / filename
        if not path.exists(): return []
        data = json.loads(path.read_text(encoding="utf-8")); data = data[key] if key else data
        return [constructor(item) if callable(constructor) and constructor is not ProgrammeSegment else ProgrammeSegment(**item) for item in data]

    def _build_shell(self) -> None:
        self._clear(); self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(1, weight=1)
        header = tk.Frame(self, bg=COLORS["bg_sidebar"], height=52); header.grid(row=0, column=0, columnspan=2, sticky="ew"); header.grid_propagate(False)
        tk.Label(header, text="VCut", bg=COLORS["bg_sidebar"], fg=COLORS["purple"], font=FONTS["title"]).pack(side="left", padx=22)
        tk.Label(header, text=f"Project: {self.project.project_name}", bg=COLORS["bg_sidebar"], fg=COLORS["text_primary"], font=FONTS["body"]).pack(side="left", padx=25)
        tk.Label(header, text="● Local", bg=COLORS["bg_sidebar"], fg=COLORS["success"], font=FONTS["body"]).pack(side="right", padx=22)
        sidebar = tk.Frame(self, bg=COLORS["bg_sidebar"], width=236); sidebar.grid(row=1, column=0, sticky="ns"); sidebar.grid_propagate(False)
        self.nav_buttons = []
        for index, label in enumerate(self.STEPS):
            button = tk.Button(sidebar, text=f"{index+1}   {label}", anchor="w", command=lambda i=index: self.show_step(i), bd=0, padx=18, pady=12, font=FONTS["body"], cursor="hand2")
            button.pack(fill="x", padx=8, pady=2); self.nav_buttons.append(button)
        tk.Label(sidebar, text="Project path", bg=COLORS["bg_sidebar"], fg=COLORS["text_muted"], font=FONTS["caption"], anchor="w").pack(side="bottom", fill="x", padx=18, pady=(0, 4))
        tk.Label(sidebar, text=str(self.project_root), bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"], font=("Consolas", 8), wraplength=200, justify="left", anchor="w").pack(side="bottom", fill="x", padx=18, pady=(0, 4))
        self.content = ttk.Frame(self, padding=24); self.content.grid(row=1, column=1, sticky="nsew"); self.content.grid_rowconfigure(1, weight=1); self.content.grid_columnconfigure(0, weight=1)
        footer = tk.Frame(self, bg=COLORS["bg_sidebar"], height=58); footer.grid(row=2, column=0, columnspan=2, sticky="ew"); footer.grid_propagate(False)
        tk.Label(footer, textvariable=self.status_var, bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"], font=FONTS["caption"]).pack(side="left", padx=20)
        ttk.Button(footer, text="Save", command=self.save_all).pack(side="right", padx=8, pady=10)
        ttk.Button(footer, text="Continue", style="Primary.TButton", command=lambda: self.show_step(min(6, self.current_step+1))).pack(side="right", padx=8, pady=10)
        ttk.Button(footer, text="Back", command=lambda: self.show_step(max(0, self.current_step-1))).pack(side="right", padx=8, pady=10)
        self.pages = [self._page_project(), self._page_cameras(), self._page_sync(), self._page_segments(), self._page_edl(), self._page_audio(), self._page_export()]

    def _page(self, title: str, description: str):
        frame = ttk.Frame(self.content); frame.grid(row=0, column=0, rowspan=2, sticky="nsew"); frame.grid_columnconfigure(0, weight=1); frame.grid_rowconfigure(2, weight=1)
        ttk.Label(frame, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 18))
        return frame

    def _field(self, parent, label, variable, row, *, values=None, check=False):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=(7, 3))
        if check: widget = ttk.Checkbutton(parent, text="Confirmed", variable=variable)
        elif values is not None: widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        else: widget = ttk.Entry(parent, textvariable=variable)
        widget.grid(row=row+1, column=0, sticky="ew", pady=(0, 4)); return widget

    def _page_project(self):
        frame = self._page("Project setup", "Confirm project details and authorization before processing footage.")
        card = ttk.Frame(frame, style="Panel.TFrame", padding=18); card.grid(row=2, column=0, sticky="new"); card.grid_columnconfigure(0, weight=1)
        self.p_name=tk.StringVar(value=self.project.project_name); self.p_event=tk.StringVar(value=self.project.event_name); self.p_date=tk.StringVar(value=self.project.event_date); self.p_share=tk.StringVar(value=self.project.sharing_type); self.p_consent=tk.BooleanVar(value=self.project.consent_confirmed)
        row=0
        for label,var,values,check in [("Project name",self.p_name,None,False),("Event name",self.p_event,None,False),("Event date",self.p_date,None,False),("Sharing classification",self.p_share,["private","public"],False),("Authorized or simulated footage",self.p_consent,None,True)]:
            self._field(card,label,var,row,values=values,check=check); row+=2
        return frame

    def _tree(self, parent, columns, widths=None):
        area=ttk.Frame(parent); area.pack(fill="both",expand=True); tree=ttk.Treeview(area,columns=columns,show="headings",selectmode="browse")
        for i,col in enumerate(columns): tree.heading(col,text=col); tree.column(col,width=(widths or {}).get(col,130),stretch=col in {"Description","Reason","File"})
        scroll=ttk.Scrollbar(area,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set); tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y"); return tree

    def _page_cameras(self):
        frame=self._page("Camera import","Add two to four MP4 recordings and assign a view role."); toolbar=ttk.Frame(frame); toolbar.grid(row=2,column=0,sticky="ew")
        ttk.Button(toolbar,text="Add camera",style="Primary.TButton",command=self.add_camera).pack(side="left"); ttk.Button(toolbar,text="Remove",command=self.remove_camera).pack(side="left",padx=8)
        holder=ttk.Frame(frame); holder.grid(row=3,column=0,sticky="nsew",pady=14); frame.grid_rowconfigure(3,weight=1); self.camera_tree=self._tree(holder,("ID","Name","Role","File","Duration","Resolution","FPS","Audio"),{"File":280}); return frame

    def _page_sync(self):
        frame=self._page("Synchronization","Enter the same clap moment in each recording; offsets are saved only after review."); controls=ttk.Frame(frame,style="Panel.TFrame",padding=18); controls.grid(row=2,column=0,sticky="new"); controls.grid_columnconfigure(1,weight=1)
        ttk.Label(controls,text="Reference camera",style="Panel.TLabel").grid(row=0,column=0,sticky="w"); self.sync_ref=tk.StringVar(); self.sync_ref_combo=ttk.Combobox(controls,textvariable=self.sync_ref,state="readonly"); self.sync_ref_combo.grid(row=0,column=1,sticky="ew",padx=10)
        ttk.Label(controls,text="Clap times (one per line: CAM001=00:03.200)",style="Panel.TLabel").grid(row=1,column=0,columnspan=2,sticky="w",pady=(16,4)); self.sync_text=tk.Text(controls,height=8,bg=COLORS["bg_input"],fg=COLORS["text_primary"],insertbackground=COLORS["text_primary"],font=FONTS["timecode"],relief="flat"); self.sync_text.grid(row=2,column=0,columnspan=2,sticky="ew")
        ttk.Button(controls,text="Calculate and save offsets",style="Primary.TButton",command=self.calculate_sync).grid(row=3,column=0,columnspan=2,sticky="w",pady=14); self.sync_result=ttk.Label(controls,text="No synchronization saved.",style="Panel.TLabel"); self.sync_result.grid(row=4,column=0,columnspan=2,sticky="w"); return frame

    def _page_segments(self):
        frame=self._page("Programme and segments","Import a UTF-8 programme CSV or add and edit segments manually."); toolbar=ttk.Frame(frame); toolbar.grid(row=2,column=0,sticky="ew")
        for text,cmd in [("Import programme CSV",self.import_programme),("Add segment",self.add_segment),("Edit",self.edit_segment),("Delete",self.delete_segment)]: ttk.Button(toolbar,text=text,style="Primary.TButton" if text.startswith("Import") else "TButton",command=cmd).pack(side="left",padx=(0,8))
        holder=ttk.Frame(frame); holder.grid(row=3,column=0,sticky="nsew",pady=14); frame.grid_rowconfigure(3,weight=1); self.programme_tree=self._tree(holder,("ID","Start","End","Type","Description","Duration"),{"Description":350}); return frame

    def _page_edl(self):
        frame=self._page("EDL review","Review every recommendation. Material changes automatically return approval to Pending."); toolbar=ttk.Frame(frame); toolbar.grid(row=2,column=0,sticky="ew")
        for text,cmd in [("Generate recommendations",self.generate_edl),("Edit selected",self.edit_edl),("Approve selected",self.approve_selected),("Approve all",self.approve_all),("Export EDL JSON",self.export_edl)]: ttk.Button(toolbar,text=text,style="Primary.TButton" if text.startswith("Generate") else "TButton",command=cmd).pack(side="left",padx=(0,8))
        self.edl_summary=ttk.Label(frame,text="No EDL generated.",style="Muted.TLabel"); self.edl_summary.grid(row=3,column=0,sticky="w",pady=(12,4)); holder=ttk.Frame(frame); holder.grid(row=4,column=0,sticky="nsew"); frame.grid_rowconfigure(4,weight=1); self.edl_tree=self._tree(holder,("ID","Timeline","Camera","Event","Transition","Approval","Reason"),{"Timeline":180,"Reason":360}); return frame

    def _page_audio(self):
        frame=self._page("Audio and text","Use one continuous audio source and configure titles, labels, credits, and subtitles."); notebook=ttk.Notebook(frame); notebook.grid(row=2,column=0,sticky="nsew"); frame.grid_rowconfigure(2,weight=1)
        audio=ttk.Frame(notebook,padding=18); text=ttk.Frame(notebook,padding=18); subs=ttk.Frame(notebook,padding=18); notebook.add(audio,text="Audio"); notebook.add(text,text="Titles and labels"); notebook.add(subs,text="Subtitles")
        self.audio_camera=tk.StringVar(value=self.project.main_audio_camera); self.audio_combo=self._field(audio,"Main audio camera",self.audio_camera,0,values=[]); self.volume=tk.DoubleVar(value=self.project.render_settings.volume); ttk.Label(audio,text="Volume",style="Panel.TLabel").grid(row=2,column=0,sticky="w",pady=(15,3)); ttk.Scale(audio,from_=0,to=2,variable=self.volume).grid(row=3,column=0,sticky="ew"); self.muted=tk.BooleanVar(value=self.project.render_settings.muted); ttk.Checkbutton(audio,text="Mute output audio",variable=self.muted).grid(row=4,column=0,sticky="w",pady=10)
        self.opening=tk.StringVar(value=self.project.opening_title); self.closing=tk.StringVar(value=self.project.closing_credits.replace("\n"," | ")); self.lower=tk.StringVar(value=self.project.lower_third); self._field(text,"Opening title",self.opening,0); self._field(text,"Closing credits",self.closing,2); self._field(text,"Lower-third label",self.lower,4)
        toolbar=ttk.Frame(subs); toolbar.pack(fill="x"); ttk.Button(toolbar,text="Import SRT",style="Primary.TButton",command=self.import_subtitles).pack(side="left"); ttk.Button(toolbar,text="Add subtitle",command=self.add_subtitle).pack(side="left",padx=8); ttk.Button(toolbar,text="Delete",command=self.delete_subtitle).pack(side="left"); holder=ttk.Frame(subs); holder.pack(fill="both",expand=True,pady=12); self.subtitle_tree=self._tree(holder,("Start","End","Text","Source"),{"Text":430}); return frame

    def _page_export(self):
        frame=self._page("Render and export","Validate readiness, render a watermarked draft, then complete the final approval gate."); self.readiness=tk.Text(frame,height=14,bg=COLORS["bg_panel"],fg=COLORS["text_primary"],font=FONTS["body"],relief="flat",padx=16,pady=16,state="disabled"); self.readiness.grid(row=2,column=0,sticky="nsew"); frame.grid_rowconfigure(2,weight=1)
        actions=ttk.Frame(frame); actions.grid(row=3,column=0,sticky="ew",pady=14); ttk.Button(actions,text="Refresh validation",command=self.refresh_export).pack(side="left"); ttk.Button(actions,text="Render draft preview",command=lambda:self.start_render(True)).pack(side="left",padx=8); self.final_button=ttk.Button(actions,text="Export final video",style="Primary.TButton",command=lambda:self.start_render(False)); self.final_button.pack(side="left")
        self.privacy=tk.BooleanVar(value=self.project.privacy_confirmed); self.copyright=tk.BooleanVar(value=self.project.copyright_confirmed); ttk.Checkbutton(actions,text="Privacy checked",variable=self.privacy,command=self.refresh_export).pack(side="left",padx=16); ttk.Checkbutton(actions,text="Copyright checked",variable=self.copyright,command=self.refresh_export).pack(side="left"); return frame

    def show_step(self,index):
        self.current_step=index
        for i,page in enumerate(self.pages):
            if i==index: page.tkraise()
            b=self.nav_buttons[i]; active=i==index; b.configure(bg=COLORS["purple_soft"] if active else COLORS["bg_sidebar"],fg=COLORS["text_primary"] if active else COLORS["text_secondary"],activebackground=COLORS["purple_soft"],activeforeground=COLORS["text_primary"])
        self.refresh_views()

    def refresh_views(self):
        if not self.pages:return
        for tree in (getattr(self,"camera_tree",None),getattr(self,"programme_tree",None),getattr(self,"edl_tree",None),getattr(self,"subtitle_tree",None)):
            if tree: tree.delete(*tree.get_children())
        for c in self.cameras: self.camera_tree.insert("","end",iid=c.id,values=(c.id,c.name,c.role,Path(c.file).name,format_timecode(c.duration),f"{c.width}×{c.height}",f"{c.fps:.2f}","Yes" if c.has_audio else "No"))
        ids=[c.id for c in self.cameras]; self.sync_ref_combo["values"]=ids; self.audio_combo["values"]=[c.id for c in self.cameras if c.has_audio]
        if not self.sync_ref.get() and ids:self.sync_ref.set(ids[0])
        for s in self.programme:self.programme_tree.insert("","end",iid=s.id,values=(s.id,format_timecode(s.start),format_timecode(s.end),s.event_type,s.description,f"{s.end-s.start:.1f}s"))
        for s in self.segments:self.edl_tree.insert("","end",iid=s.id,values=(s.id,f"{format_timecode(s.timeline_start)} – {format_timecode(s.timeline_end)}",s.selected_camera,s.event_type,s.transition,"Approved" if s.approved else "Pending",s.reason))
        used=[s.selected_camera for s in self.segments]; switches=sum(a!=b for a,b in zip(used,used[1:])); self.edl_summary.configure(text=f"Segments: {len(self.segments)}   •   Cameras used: {len(set(used))}   •   Switches: {switches}   •   Approved: {sum(s.approved for s in self.segments)} of {len(self.segments)}")
        for i,s in enumerate(self.subtitles):self.subtitle_tree.insert("","end",iid=str(i),values=(format_timecode(s.start),format_timecode(s.end),s.text,s.source))
        if self.current_step==6:self.refresh_export()

    def add_camera(self):
        if len(self.cameras)>=4:return self._error("VCut supports at most four cameras.")
        path=filedialog.askopenfilename(title="Add MP4 camera",filetypes=[("MP4 video","*.mp4")]);
        if not path:return
        camera_id=f"CAM{len(self.cameras)+1:03d}"; name=simpledialog.askstring("Camera name","Camera name:",initialvalue=f"Camera {len(self.cameras)+1}",parent=self) or camera_id; role=simpledialog.askstring("Camera role","Role: wide, front, front-left, front-right, or side",initialvalue="wide" if not self.cameras else "front",parent=self) or "front"
        self._background(lambda:probe_media(Path(path),camera_id,name,role),lambda camera:(self.cameras.append(camera),self.save_all(),self.refresh_views()),"Inspecting camera…")

    def remove_camera(self):
        selected=self.camera_tree.selection()
        if selected and messagebox.askyesno("Remove camera","Remove the selected camera reference? Source footage will not be deleted."): self.cameras=[c for c in self.cameras if c.id!=selected[0]]; self.segments=[s for s in self.segments if s.selected_camera!=selected[0]]; self.save_all(); self.refresh_views()

    def calculate_sync(self):
        try:
            values={}
            for line in self.sync_text.get("1.0","end").splitlines():
                if line.strip(): key,value=line.split("=",1); values[key.strip()]=parse_timecode(value.strip())
            self.synchronization=SynchronizationService().calculate_offsets(values,self.sync_ref.get()); self.synchronization.approved=True; atomic_write_json(self.project_root/"synchronization.json",to_dict(self.synchronization)); self.sync_result.configure(text="Saved offsets: "+", ".join(f"{k} {v:+.3f}s" for k,v in self.synchronization.offsets.items())); self.status_var.set("Synchronization saved.")
        except Exception as exc:self._error(exc)

    def import_programme(self):
        path=filedialog.askopenfilename(filetypes=[("CSV programme","*.csv")]);
        if path:
            try:self.programme=read_programme(Path(path)); self.segments=[]; self.save_all(); self.refresh_views()
            except VCutError as exc:self._error(exc)

    def _segment_dialog(self, existing=None):
        sid=simpledialog.askstring("Segment","Segment ID:",initialvalue=existing.id if existing else f"SEG{len(self.programme)+1:03d}",parent=self)
        if not sid:return None
        start=parse_timecode(simpledialog.askstring("Segment","Start time:",initialvalue=format_timecode(existing.start) if existing else "00:00:00.000",parent=self)); end=parse_timecode(simpledialog.askstring("Segment","End time:",initialvalue=format_timecode(existing.end) if existing else "00:00:10.000",parent=self)); event=simpledialog.askstring("Segment","Event type:",initialvalue=existing.event_type if existing else "performance",parent=self) or "performance"; desc=simpledialog.askstring("Segment","Description:",initialvalue=existing.description if existing else "",parent=self) or ""; return ProgrammeSegment(sid,start,end,event.lower(),desc)

    def add_segment(self):
        try:
            item=self._segment_dialog();
            if item:self.programme.append(item);self.programme.sort(key=lambda s:s.start);self.segments=[];self.save_all();self.refresh_views()
        except Exception as exc:self._error(exc)

    def edit_segment(self):
        sel=self.programme_tree.selection();
        if not sel:return
        try:
            old=next(s for s in self.programme if s.id==sel[0]); new=self._segment_dialog(old)
            if new:self.programme=[new if s.id==old.id else s for s in self.programme];self.programme.sort(key=lambda s:s.start);self.segments=[];self.save_all();self.refresh_views()
        except Exception as exc:self._error(exc)

    def delete_segment(self):
        sel=self.programme_tree.selection();
        if sel and messagebox.askyesno("Delete segment","Delete the selected segment?"):self.programme=[s for s in self.programme if s.id!=sel[0]];self.segments=[];self.save_all();self.refresh_views()

    def generate_edl(self):
        try:
            if not self.synchronization:raise ValueError("Save synchronization before generating recommendations.")
            self.segments=self.edl_service.generate(self.project,self.cameras,self.programme,self.synchronization);self.save_all();self.refresh_views();self.status_var.set("Explainable recommendations generated. Review every segment.")
        except Exception as exc:self._error(exc)

    def edit_edl(self):
        sel=self.edl_tree.selection();
        if not sel:return
        segment=next(s for s in self.segments if s.id==sel[0]); camera=simpledialog.askstring("Edit EDL segment","Selected camera ID:",initialvalue=segment.selected_camera,parent=self); transition=simpledialog.askstring("Edit EDL segment","Transition (cut or fade):",initialvalue=segment.transition,parent=self); reason=simpledialog.askstring("Edit EDL segment","Editing reason:",initialvalue=segment.reason,parent=self)
        if camera and transition and reason:self.segments=[self.edl_service.update_segment(s,{"selected_camera":camera,"transition":transition,"reason":reason}) if s.id==segment.id else s for s in self.segments];self.save_all();self.refresh_views()

    def approve_selected(self):
        sel=self.edl_tree.selection();
        if sel:self.segments=[self.edl_service.update_segment(s,{"approved":True}) if s.id==sel[0] else s for s in self.segments];self.save_all();self.refresh_views()

    def approve_all(self):
        if self.segments and messagebox.askyesno("Approve all reviewed segments","Confirm that you reviewed every camera choice and edit?"): self.segments=[self.edl_service.update_segment(s,{"approved":True}) for s in self.segments];self.save_all();self.refresh_views()

    def export_edl(self):
        if not self.segments:return
        path=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")],initialfile="edl.json")
        if path:self.edl_service.save(Path(path),self.project,self.cameras,self.segments,self.subtitles);self.status_var.set("EDL JSON exported.")

    def import_subtitles(self):
        path=filedialog.askopenfilename(filetypes=[("SubRip subtitles","*.srt")]);
        if path:
            try:self.subtitles=import_srt(Path(path));self.save_all();self.refresh_views();warnings=overlap_warnings(self.subtitles);self.status_var.set(warnings[0] if warnings else "Subtitles imported.")
            except VCutError as exc:self._error(exc)

    def add_subtitle(self):
        try:
            start=parse_timecode(simpledialog.askstring("Subtitle","Start:",initialvalue="00:00:00.000",parent=self));end=parse_timecode(simpledialog.askstring("Subtitle","End:",initialvalue="00:00:03.000",parent=self));text=simpledialog.askstring("Subtitle","Text:",parent=self)
            if text:self.subtitles.append(SubtitleEntry(start,end,text));self.save_all();self.refresh_views()
        except Exception as exc:self._error(exc)

    def delete_subtitle(self):
        sel=self.subtitle_tree.selection();
        if sel:self.subtitles.pop(int(sel[0]));self.save_all();self.refresh_views()

    def _apply_form(self):
        if not self.project:return
        self.project.project_name=self.p_name.get().strip();self.project.event_name=self.p_event.get().strip();self.project.event_date=self.p_date.get().strip();self.project.sharing_type=self.p_share.get();self.project.consent_confirmed=self.p_consent.get();self.project.main_audio_camera=self.audio_camera.get();self.project.render_settings.volume=self.volume.get();self.project.render_settings.muted=self.muted.get();self.project.opening_title=self.opening.get();self.project.closing_credits=self.closing.get().replace(" | ","\n");self.project.lower_third=self.lower.get();self.project.privacy_confirmed=getattr(self,"privacy",tk.BooleanVar(value=False)).get();self.project.copyright_confirmed=getattr(self,"copyright",tk.BooleanVar(value=False)).get()

    def save_all(self):
        if not self.project_root:return
        try:
            self._apply_form();self.service.save_project(self.project_root,self.project);self.service.save_cameras(self.project_root,self.cameras);atomic_write_json(self.project_root/"programme.json",[to_dict(s) for s in self.programme]);atomic_write_json(self.project_root/"subtitles.json",[to_dict(s) for s in self.subtitles]);self.edl_service.save(self.project_root/"edl.json",self.project,self.cameras,self.segments,self.subtitles);self.status_var.set("Saved locally.")
        except Exception as exc:self._error(exc)

    def refresh_export(self):
        self._apply_form();issues=self.validation.validate_final(self.project,self.cameras,self.segments,self.subtitles);lines=["PROJECT READINESS",""]+[f"{'✓' if i.severity!='error' else '✕'} {i.code}: {i.message}" for i in issues]
        if not issues:lines.append("✓ All final export requirements are satisfied.")
        self.readiness.configure(state="normal");self.readiness.delete("1.0","end");self.readiness.insert("1.0","\n".join(lines));self.readiness.configure(state="disabled");self.final_button.configure(state="disabled" if blocking(issues) else "normal")

    def start_render(self,preview):
        self.save_all();self._background(lambda:Renderer().render(self.project_root,self.project,self.cameras,self.segments,self.subtitles,preview=preview,progress=lambda msg:self.worker_queue.put(("status",msg))),lambda path:self._render_done(path),"Starting render…")

    def _render_done(self,path):
        self.status_var.set(f"Render complete: {path}")
        if messagebox.askyesno("Render complete",f"Open the rendered video?\n\n{path}"): os.startfile(path)

    def _background(self,work,success,status):
        self.status_var.set(status)
        def runner():
            try:self.worker_queue.put(("success",(success,work())))
            except Exception as exc:self.worker_queue.put(("error",exc))
        threading.Thread(target=runner,daemon=True).start();self.after(100,self._poll_worker)

    def _poll_worker(self):
        try:
            kind,payload=self.worker_queue.get_nowait()
            if kind=="status":self.status_var.set(str(payload));self.after(100,self._poll_worker)
            elif kind=="success":callback,value=payload;callback(value)
            else:self._error(payload)
        except queue.Empty:self.after(100,self._poll_worker)

    def _error(self,error):
        self.status_var.set(str(error));messagebox.showerror("VCut",str(error),parent=self)


def main() -> None:
    try:
        VCutApp().mainloop()
    except tk.TclError as exc:
        raise SystemExit(
            "VCut could not open its desktop window. Install a standard Python 3.11+ "
            f"distribution with Tcl/Tk support, then try again. Technical detail: {exc}"
        ) from None


if __name__ == "__main__": main()
