from __future__ import annotations

from tkinter import ttk

COLORS = {
    "bg_app": "#121116", "bg_sidebar": "#18161F", "bg_panel": "#211E29",
    "bg_panel_alt": "#292532", "bg_input": "#17151D", "border": "#3A3545",
    "purple": "#8B5CF6", "purple_hover": "#9F7AEA", "purple_soft": "#302747",
    "text_primary": "#F4F1FA", "text_secondary": "#B8B2C4", "text_muted": "#817A8F",
    "success": "#4CC38A", "warning": "#F2B84B", "error": "#F06A73", "info": "#65A9FF",
}
FONTS = {
    "title": ("Segoe UI", 18, "bold"), "page_title": ("Segoe UI", 22, "bold"),
    "section": ("Segoe UI", 14, "bold"), "body": ("Segoe UI", 11),
    "caption": ("Segoe UI", 9), "timecode": ("Consolas", 10),
}


def apply_theme(root) -> None:
    root.configure(bg=COLORS["bg_app"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=COLORS["bg_app"], foreground=COLORS["text_primary"], fieldbackground=COLORS["bg_input"], font=FONTS["body"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"])
    style.configure("TFrame", background=COLORS["bg_app"])
    style.configure("Panel.TFrame", background=COLORS["bg_panel"], borderwidth=1, relief="solid")
    style.configure("TLabel", background=COLORS["bg_app"], foreground=COLORS["text_primary"])
    style.configure("Panel.TLabel", background=COLORS["bg_panel"], foreground=COLORS["text_primary"])
    style.configure("Muted.TLabel", foreground=COLORS["text_secondary"])
    style.configure("Title.TLabel", font=FONTS["page_title"])
    style.configure("Section.TLabel", font=FONTS["section"])
    style.configure("Primary.TButton", background=COLORS["purple"], foreground=COLORS["text_primary"], padding=(14, 8), borderwidth=0)
    style.map("Primary.TButton", background=[("active", COLORS["purple_hover"]), ("disabled", COLORS["border"])])
    style.configure("TButton", background=COLORS["bg_panel_alt"], foreground=COLORS["text_primary"], padding=(12, 7))
    style.map("TButton", background=[("active", COLORS["purple_soft"])])
    style.configure("Treeview", background=COLORS["bg_panel"], fieldbackground=COLORS["bg_panel"], foreground=COLORS["text_primary"], rowheight=32, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["bg_panel_alt"], foreground=COLORS["text_primary"], padding=7)
    style.map("Treeview", background=[("selected", COLORS["purple_soft"])])
    style.configure("TEntry", padding=7)
    style.configure("TCombobox", padding=6)
    style.configure("TNotebook", background=COLORS["bg_panel"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["bg_panel_alt"], foreground=COLORS["text_secondary"], padding=(14, 8))
    style.map("TNotebook.Tab", background=[("selected", COLORS["purple_soft"])], foreground=[("selected", COLORS["text_primary"])])
