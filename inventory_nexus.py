"""ODYSSEY // Inventory Nexus

Local-first resale operations dashboard.  It keeps inventory and photo metadata
in SQLite, opens broad marketplace research searches in the user's browser, and
stores manually confirmed comparable sales for transparent pricing.

Optional dependencies:
    python3 -m pip install requests pillow

No API key is embedded in this file.  If OPENAI_API_KEY is present, the optional
listing helper can use it; otherwise the app remains fully local.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from urllib.parse import quote_plus

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import requests
except ImportError:
    requests = None


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "inventory.db"
PHOTO_DIR = APP_DIR / "item_photos"
STATUSES = ("In Stock", "Listed", "Sold")
CONDITIONS = ("New With Tags", "New Without Tags", "Excellent", "Good", "Fair")
CATEGORIES = (
    "Sweatshirt",
    "Crop Top",
    "Cardigan",
    "Jacket",
    "T Shirt",
    "Long Sleeve Shirt",
    "Other Tops",
    "Bottoms",
    "Outerwear",
    "Vinyl",
    "Cassette",
    "CD",
    "Ornament",
    "Accessories",
    "Other Media",
    "Other Memorabilia",
)
MARKETS = ("eBay", "Poshmark", "Mercari", "Depop", "Google Images")

BG = "#071321"
PANEL = "#0d1d31"
PANEL_2 = "#112940"
CYAN = "#8fe8ff"
CYAN_DARK = "#1f8eaf"
PURPLE = "#9c73e8"
TEXT = "#d7e8f1"
MUTED = "#7895a9"
GOLD = "#f1c37a"
GREEN = "#7de6c1"


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class InventoryDatabase:
    """SQLite persistence for inventory, uploaded photos, and market comps."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.create_tables()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_tables(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS inventory (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL, brand TEXT, category TEXT, condition TEXT,
                    size TEXT, purchase_price REAL, suggested_price REAL,
                    description TEXT, poshmark_title TEXT, depop_title TEXT,
                    mercari_title TEXT, hashtags TEXT, status TEXT DEFAULT 'In Stock',
                    created_at TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS item_images (
                    image_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL, sha256 TEXT NOT NULL, image_role TEXT,
                    created_at TIMESTAMP, UNIQUE(item_id, sha256)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS market_comps (
                    comp_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL,
                    marketplace TEXT, title TEXT, url TEXT, price REAL, shipping REAL,
                    sold INTEGER DEFAULT 0, condition TEXT, match_score REAL,
                    retrieved_at TIMESTAMP
                )"""
            )
            conn.commit()

    def list_items(self, search: str = "") -> list[sqlite3.Row]:
        q = "SELECT * FROM inventory WHERE 1=1"
        params: list[object] = []
        if search:
            q += " AND (title LIKE ? OR brand LIKE ? OR category LIKE ? OR description LIKE ?)"
            term = f"%{search}%"
            params.extend([term] * 4)
        q += " ORDER BY created_at DESC, item_id DESC"
        with self.connect() as conn:
            return list(conn.execute(q, params))

    def get_item(self, item_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM inventory WHERE item_id = ?", (item_id,)).fetchone()

    def add_item(self, data: dict[str, object]) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO inventory
                (title, brand, category, condition, size, purchase_price, suggested_price,
                 description, poshmark_title, depop_title, mercari_title, hashtags, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', ?, ?)""",
                (data["title"], data["brand"], data["category"], data["condition"], data["size"],
                 data["purchase_price"], data.get("suggested_price"), data.get("description", ""),
                 data.get("status", "In Stock"), now()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_item(self, item_id: int, data: dict[str, object]) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE inventory SET title=?, brand=?, category=?, condition=?, size=?,
                purchase_price=?, suggested_price=?, description=?, status=? WHERE item_id=?""",
                (data["title"], data["brand"], data["category"], data["condition"], data["size"],
                 data["purchase_price"], data.get("suggested_price"), data.get("description", ""),
                 data.get("status", "In Stock"), item_id),
            )
            conn.commit()

    def update_generated(self, item_id: int, values: dict[str, object]) -> None:
        if not values:
            return
        fields = ", ".join(f"{key}= ?" for key in values)
        with self.connect() as conn:
            conn.execute(f"UPDATE inventory SET {fields} WHERE item_id=?", (*values.values(), item_id))
            conn.commit()

    def mark_sold(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE inventory SET status='Sold' WHERE item_id=?", (item_id,))
            conn.commit()

    def add_photo(self, item_id: int, source: str, role: str = "reference") -> bool:
        path = Path(source)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target_dir = PHOTO_DIR / str(item_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest[:16]}{path.suffix.lower()}"
        shutil.copy2(path, target)
        with self.connect() as conn:
            try:
                conn.execute("INSERT INTO item_images (item_id,file_path,sha256,image_role,created_at) VALUES (?,?,?,?,?)",
                             (item_id, str(target), digest, role, now()))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def photos(self, item_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM item_images WHERE item_id=? ORDER BY image_id", (item_id,)))

    def add_comp(self, item_id: int, market: str, title: str, url: str, price: float,
                 shipping: float, sold: bool, condition: str, score: float) -> None:
        with self.connect() as conn:
            conn.execute("""INSERT INTO market_comps
                (item_id,marketplace,title,url,price,shipping,sold,condition,match_score,retrieved_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (item_id, market, title, url, price, shipping, int(sold), condition, score, now()))
            conn.commit()

    def comps(self, item_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM market_comps WHERE item_id=? ORDER BY retrieved_at DESC", (item_id,)))


class MarketRadar:
    """Builds broad, transparent research URLs without pretending to have live data."""

    @staticmethod
    def query(item: sqlite3.Row) -> str:
        bits = [item["brand"], item["title"], item["size"], item["condition"]]
        return " ".join(str(x).strip() for x in bits if x).strip()

    @classmethod
    def links(cls, item: sqlite3.Row) -> list[tuple[str, str]]:
        q = quote_plus(cls.query(item))
        return [
            ("eBay active", f"https://www.ebay.com/sch/i.html?_nkw={q}"),
            ("eBay sold", f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1"),
            ("Poshmark", f"https://poshmark.com/search?query={q}"),
            ("Mercari", f"https://www.mercari.com/search/?keyword={q}"),
            ("Depop", f"https://www.depop.com/search/?q={q}"),
            ("Google Images", f"https://www.google.com/search?tbm=isch&q={q}"),
        ]

    @classmethod
    def open_all(cls, item: sqlite3.Row) -> None:
        for _name, url in cls.links(item):
            webbrowser.open_new_tab(url)

    @classmethod
    def summary(cls, item: sqlite3.Row, comps: list[sqlite3.Row]) -> dict[str, object]:
        sold = [float(c["price"] or 0) + float(c["shipping"] or 0) for c in comps if c["sold"]]
        active = [float(c["price"] or 0) + float(c["shipping"] or 0) for c in comps if not c["sold"]]
        values = sold or active
        median = sorted(values)[len(values) // 2] if values else None
        purchase = float(item["purchase_price"] or 0)
        suggested = round(max(8, median * 0.96 if median else purchase * 3.2), 2)
        return {"sold_count": len(sold), "active_count": len(active), "median": median,
                "suggested": suggested, "confidence": min(98, 38 + len(comps) * 6)}


class ListingAI:
    """Optional listing helper. Local templates work without any network access."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()

    def generate(self, item: sqlite3.Row) -> dict[str, str]:
        brand = item["brand"] or "Unbranded"
        title = item["title"] or "Resale item"
        category = item["category"] or "Fashion"
        condition = item["condition"] or "Good"
        size = item["size"] or "See measurements"
        tags = " ".join(f"#{x.lower().replace(' ', '')}" for x in (brand, category, "resale", "thrifted"))
        base = f"{brand} {title} Size {size}".strip()[:77]
        body = f"{base}\n\nBrand: {brand}\nCategory: {category}\nSize: {size}\nCondition: {condition}\n\n{item['description'] or 'Please review photos and details before purchasing.'}"
        return {"poshmark_title": base, "depop_title": f"{brand} {title} | {category}"[:77],
                "mercari_title": base, "poshmark_description": body, "depop_description": body,
                "mercari_description": body, "hashtags": tags}


class OdysseyApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ODYSSEY // Inventory Nexus")
        self.geometry("1440x900")
        self.minsize(1120, 720)
        self.configure(bg=BG)
        self.db = InventoryDatabase()
        self.radar = MarketRadar()
        self.ai = ListingAI()
        self.selected_item_id: int | None = None
        self.thumb_refs: list[object] = []
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="SYSTEM READY // LOCAL SQLITE ONLINE")
        self._style()
        self._build()
        self.refresh()

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Helvetica", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Helvetica", 9))
        style.configure("Header.TLabel", background=BG, foreground=CYAN, font=("Helvetica", 16, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=CYAN, font=("Helvetica", 22, "bold"))
        style.configure("TButton", background=PANEL_2, foreground=CYAN, padding=8, borderwidth=1)
        style.map("TButton", background=[("active", CYAN_DARK)], foreground=[("active", "white")])
        style.configure("TEntry", fieldbackground="#091827", foreground=TEXT, insertcolor=CYAN)
        style.configure("TCombobox", fieldbackground="#091827", foreground=TEXT)
        style.configure("Treeview", background="#091827", fieldbackground="#091827", foreground=TEXT, rowheight=30)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=CYAN)

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=26, pady=(22, 14))
        ttk.Label(top, text="◉ ODYSSEY", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=" // INVENTORY NEXUS  •  RESALE OPS v3.0", style="Header.TLabel").pack(side="left", padx=18)
        ttk.Label(top, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_nav(body)
        self._build_center(body)
        self._build_right(body)
        ttk.Label(self, text="LOCAL-FIRST // MARKET LINKS ARE OPENED IN YOUR BROWSER // COMPS REQUIRE USER CONFIRMATION", style="Muted.TLabel").pack(anchor="w", padx=28, pady=(0, 12))

    def _build_nav(self, parent: ttk.Frame) -> None:
        nav = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        nav.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        ttk.Label(nav, text="NEXUS MODULES", foreground=CYAN, background=PANEL, font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(4, 16))
        for text in ("DATA ENTRY", "PLATFORM GEN", "AI PRICING", "PHOTO MATCH", "MARKET RADAR"):
            ttk.Button(nav, text=text, command=lambda t=text: self._module_action(t), width=20).pack(fill="x", pady=5)
        ttk.Separator(nav).pack(fill="x", pady=26)
        ttk.Label(nav, text="ACTIONS", foreground=GOLD, background=PANEL, font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Button(nav, text="＋ ADD ITEM", command=self.add_item_dialog).pack(fill="x", pady=(12, 5))
        ttk.Button(nav, text="MARK SOLD", command=self.mark_sold).pack(fill="x", pady=5)
        ttk.Button(nav, text="⟳ REFRESH COMPS", command=self.refresh_market).pack(fill="x", pady=5)

    def _build_center(self, parent: ttk.Frame) -> None:
        center = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        center.grid(row=0, column=1, sticky="nsew")
        center.rowconfigure(2, weight=1)
        center.columnconfigure(0, weight=1)
        ttk.Label(center, text="CORE INVENTORY DB", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        filters = ttk.Frame(center, style="Panel.TFrame")
        filters.grid(row=1, column=0, sticky="ew", pady=14)
        filters.columnconfigure(0, weight=1)
        ttk.Entry(filters, textvariable=self.search_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(filters, text="SEARCH", command=self.refresh).grid(row=0, column=1, padx=4)
        ttk.Button(filters, text="OPEN MARKET RADAR", command=self.refresh_market).grid(row=0, column=2, padx=4)
        table_frame = ttk.Frame(center, style="Panel.TFrame")
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        cols = ("id", "title", "brand", "category", "condition", "cost", "suggested", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        headings = {"id":"ID", "title":"ITEM / MODEL", "brand":"BRAND", "category":"CATEGORY", "condition":"COND", "cost":"BUY PRICE", "suggested":"SUGGESTED", "status":"STATUS"}
        widths = {"id":50, "title":280, "brand":130, "category":120, "condition":125, "cost":95, "suggested":100, "status":90}
        for col in cols:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda _e: self.edit_item())

    def _build_right(self, parent: ttk.Frame) -> None:
        right = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        right.grid(row=0, column=2, sticky="nsew", padx=(14, 0))
        right.columnconfigure(0, weight=1)
        self.analysis_title = ttk.Label(right, text="AI MARKET ANALYSIS // PRICE CHECK", style="Header.TLabel", wraplength=320)
        self.analysis_title.grid(row=0, column=0, sticky="w")
        self.analysis_text = tk.Text(right, height=13, width=38, bg="#091827", fg=TEXT, insertbackground=CYAN, relief="flat", wrap="word")
        self.analysis_text.grid(row=1, column=0, sticky="ew", pady=10)
        ttk.Button(right, text="OPEN ALL MARKET SEARCHES", command=self.open_searches).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(right, text="ADD CONFIRMED COMPARABLE", command=self.add_comp_dialog).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Separator(right).grid(row=4, column=0, sticky="ew", pady=18)
        ttk.Label(right, text="PHOTO MATCH / ITEM EVIDENCE", style="Header.TLabel", wraplength=320).grid(row=5, column=0, sticky="w")
        self.photo_frame = ttk.Frame(right, style="Panel.TFrame")
        self.photo_frame.grid(row=6, column=0, sticky="ew", pady=8)
        ttk.Button(right, text="UPLOAD ITEM PHOTOS", command=self.upload_photos).grid(row=7, column=0, sticky="ew", pady=4)
        ttk.Button(right, text="SEARCH IMAGE + IDENTITY", command=self.open_image_search).grid(row=8, column=0, sticky="ew", pady=4)
        ttk.Separator(right).grid(row=9, column=0, sticky="ew", pady=18)
        ttk.Label(right, text="PLATFORM GENERATOR", style="Header.TLabel").grid(row=10, column=0, sticky="w")
        ttk.Button(right, text="GENERATE LISTING COPY", command=self.generate_listing).grid(row=11, column=0, sticky="ew", pady=6)
        self.listing_text = tk.Text(right, height=8, width=38, bg="#091827", fg=TEXT, relief="flat", wrap="word")
        self.listing_text.grid(row=12, column=0, sticky="ew")

    def _module_action(self, module: str) -> None:
        if module in ("MARKET RADAR", "AI PRICING"):
            self.refresh_market()
        elif module == "PHOTO MATCH":
            self.upload_photos()
        elif module == "PLATFORM GEN":
            self.generate_listing()
        else:
            self.add_item_dialog()

    def selected(self) -> sqlite3.Row | None:
        selected = self.tree.selection()
        return self.db.get_item(int(selected[0])) if selected else None

    def refresh(self) -> None:
        for child in self.tree.get_children():
            self.tree.delete(child)
        for row in self.db.list_items(self.search_var.get().strip()):
            self.tree.insert("", "end", iid=str(row["item_id"]), values=(row["item_id"], row["title"], row["brand"], row["category"], row["condition"], self.money(row["purchase_price"]), self.money(row["suggested_price"]), row["status"]))
        if self.tree.get_children() and not self.tree.selection():
            self.tree.selection_set(self.tree.get_children()[0])
            self.on_select(None)

    def on_select(self, _event: object) -> None:
        item = self.selected()
        if item:
            self.selected_item_id = int(item["item_id"])
            self.render_analysis(item)
            self.render_photos(item)

    def render_analysis(self, item: sqlite3.Row) -> None:
        summary = self.radar.summary(item, self.db.comps(int(item["item_id"])))
        median = self.money(summary["median"]) if summary["median"] else "Awaiting comps"
        text = (f"ANALYZING  {self.radar.query(item)}\n\n"
                f"MARKET MEDIAN:  {median}\n"
                f"SOLD COMPS:      {summary['sold_count']}\n"
                f"ACTIVE LISTINGS: {summary['active_count']}\n"
                f"CONFIDENCE:      {summary['confidence']}%\n\n"
                f"SUGGESTED:       {self.money(summary['suggested'])}\n\n"
                "Pricing uses confirmed comps, shipping-adjusted totals, and a transparent confidence score.\n\n"
                "Use OPEN ALL MARKET SEARCHES to research current listings, then capture confirmed comps.")
        self.analysis_text.configure(state="normal")
        self.analysis_text.delete("1.0", "end")
        self.analysis_text.insert("1.0", text)
        self.analysis_text.configure(state="disabled")

    def render_photos(self, item: sqlite3.Row) -> None:
        for child in self.photo_frame.winfo_children():
            child.destroy()
        self.thumb_refs.clear()
        photos = self.db.photos(int(item["item_id"]))
        if not photos:
            ttk.Label(self.photo_frame, text="NO PHOTO EVIDENCE UPLOADED", style="Muted.TLabel").pack(anchor="w")
            return
        for photo in photos[:4]:
            path = Path(photo["file_path"])
            if Image and ImageTk and path.exists():
                try:
                    img = Image.open(path).convert("RGB")
                    img.thumbnail((68, 68))
                    thumb = ImageTk.PhotoImage(img)
                    self.thumb_refs.append(thumb)
                    ttk.Label(self.photo_frame, image=thumb).pack(side="left", padx=3)
                    continue
                except Exception:
                    pass
            ttk.Label(self.photo_frame, text="IMG", width=7).pack(side="left", padx=3)
        ttk.Label(self.photo_frame, text=f"{len(photos)} FILE(S) // VISUAL FINGERPRINT READY", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    def add_item_dialog(self, existing: sqlite3.Row | None = None) -> None:
        win = tk.Toplevel(self)
        win.title("ODYSSEY // Edit Inventory Card" if existing else "ODYSSEY // New Inventory Card")
        win.configure(bg=BG)
        win.geometry("520x560")
        fields: dict[str, tk.StringVar] = {}
        form = ttk.Frame(win, padding=18)
        form.pack(fill="both", expand=True)
        for row, (key, label) in enumerate((("title", "Title / Model"), ("brand", "Brand"), ("size", "Size"), ("purchase_price", "Buy Price"))):
            fields[key] = tk.StringVar(value="" if existing is None else str(existing[key] or ""))
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=7)
            ttk.Entry(form, textvariable=fields[key], width=42).grid(row=row, column=1, sticky="ew", pady=7)
        fields["category"] = tk.StringVar(value=(existing["category"] if existing else "Outerwear") or "Outerwear")
        fields["condition"] = tk.StringVar(value=(existing["condition"] if existing else "Good") or "Good")
        fields["status"] = tk.StringVar(value=(existing["status"] if existing else "In Stock") or "In Stock")
        for row, key, label, values in ((4, "category", "Category", CATEGORIES), (5, "condition", "Condition", CONDITIONS), (6, "status", "Status", STATUSES)):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=7)
            ttk.Combobox(form, textvariable=fields[key], values=values, state="readonly", width=39).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Label(form, text="Notes / identity clues").grid(row=7, column=0, sticky="nw", pady=7)
        notes = tk.Text(form, height=7, bg="#091827", fg=TEXT, relief="flat", wrap="word")
        notes.grid(row=7, column=1, sticky="ew", pady=7)
        if existing:
            notes.insert("1.0", existing["description"] or "")
        form.columnconfigure(1, weight=1)
        def save() -> None:
            try:
                price = float(fields["purchase_price"].get())
                if price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid price", "Buy Price must be a non-negative number.", parent=win)
                return
            if not fields["title"].get().strip():
                messagebox.showerror("Missing title", "Title / Model is required.", parent=win)
                return
            data = {**{k: v.get().strip() for k, v in fields.items()}, "purchase_price": price, "description": notes.get("1.0", "end").strip()}
            if existing:
                self.db.update_item(int(existing["item_id"]), data)
                item_id = int(existing["item_id"])
            else:
                item_id = self.db.add_item(data)
            win.destroy()
            self.refresh()
            self.tree.selection_set(str(item_id))
            self.on_select(None)
        ttk.Button(form, text="SAVE TO CORE INVENTORY", command=save).grid(row=8, column=0, columnspan=2, sticky="ew", pady=18)

    def edit_item(self) -> None:
        item = self.selected()
        if not item:
            return
        self.add_item_dialog(item)

    def upload_photos(self) -> None:
        item = self.selected()
        if not item:
            messagebox.showinfo("Select an item", "Select an inventory card before uploading photos.")
            return
        paths = filedialog.askopenfilenames(title="Upload item photographs", filetypes=(("Images", "*.png *.jpg *.jpeg *.webp *.heic"), ("All files", "*.*")))
        added = 0
        for path in paths:
            try:
                added += int(self.db.add_photo(int(item["item_id"]), path))
            except OSError as exc:
                messagebox.showerror("Photo upload", str(exc))
        self.render_photos(item)
        self.status_var.set(f"PHOTO MATCH // {added} NEW IMAGE(S) INDEXED")

    def open_searches(self) -> None:
        item = self.selected()
        if not item:
            return
        self.radar.open_all(item)
        self.status_var.set("MARKET RADAR // SEARCH WINDOWS OPENED")

    def open_image_search(self) -> None:
        item = self.selected()
        if not item:
            return
        photos = self.db.photos(int(item["item_id"]))
        if not photos:
            messagebox.showinfo(
                "No item photos",
                "Upload at least one item photo before using SEARCH IMAGE + IDENTITY.",
            )
            return

        opened = 0
        for photo in photos:
            path = Path(photo["file_path"])
            if path.exists():
                webbrowser.open_new_tab(path.as_uri())
                opened += 1

        q = quote_plus(self.radar.query(item))
        webbrowser.open_new_tab(f"https://www.google.com/search?tbm=isch&q={q}")
        webbrowser.open_new_tab("https://lens.google.com/")
        self.status_var.set(f"PHOTO MATCH // {opened} UPLOADED IMAGE(S) OPENED FOR REVERSE SEARCH")

    def refresh_market(self) -> None:
        item = self.selected()
        if not item:
            return
        self.status_var.set("MARKET RADAR // PREPARING MULTI-MARKET RESEARCH")
        threading.Thread(target=self._market_worker, args=(int(item["item_id"]),), daemon=True).start()

    def _market_worker(self, item_id: int) -> None:
        item = self.db.get_item(item_id)
        if not item:
            return
        self.radar.open_all(item)
        self.after(0, lambda: (self.status_var.set("MARKET RADAR // 6 SEARCH CHANNELS OPENED"), self.render_analysis(item)))

    def add_comp_dialog(self) -> None:
        item = self.selected()
        if not item:
            return
        win = tk.Toplevel(self)
        win.title("Capture Confirmed Comparable")
        win.configure(bg=BG)
        form = ttk.Frame(win, padding=18)
        form.pack(fill="both", expand=True)
        vals = {key: tk.StringVar() for key in ("market", "title", "url", "price", "shipping", "condition", "score")}
        vals["market"].set("eBay")
        vals["condition"].set(item["condition"] or "Used")
        vals["score"].set("80")
        rows = (("market", "Marketplace"), ("title", "Listing title"), ("url", "Listing URL"), ("price", "Price"), ("shipping", "Shipping"), ("condition", "Condition"), ("score", "Match score %"))
        for row, (key, label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            if key == "market":
                ttk.Combobox(form, textvariable=vals[key], values=MARKETS, state="readonly", width=40).grid(row=row, column=1, sticky="ew")
            else:
                ttk.Entry(form, textvariable=vals[key], width=43).grid(row=row, column=1, sticky="ew")
        form.columnconfigure(1, weight=1)
        def save() -> None:
            try:
                price, shipping, score = float(vals["price"].get()), float(vals["shipping"].get() or 0), float(vals["score"].get())
            except ValueError:
                messagebox.showerror("Invalid comp", "Price, shipping, and match score must be numbers.", parent=win)
                return
            self.db.add_comp(int(item["item_id"]), vals["market"].get(), vals["title"].get(), vals["url"].get(), price, shipping, True, vals["condition"].get(), score)
            summary = self.radar.summary(item, self.db.comps(int(item["item_id"])))
            self.db.update_generated(int(item["item_id"]), {"suggested_price": summary["suggested"]})
            win.destroy()
            self.refresh()
            self.render_analysis(self.db.get_item(int(item["item_id"])))
        ttk.Button(form, text="SAVE CONFIRMED SOLD COMP", command=save).grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=15)

    def generate_listing(self) -> None:
        item = self.selected()
        if not item:
            return
        result = self.ai.generate(item)
        text = f"POSHMARK\n{result['poshmark_title']}\n\n{result['poshmark_description']}\n\nTAGS\n{result['hashtags']}"
        self.listing_text.delete("1.0", "end")
        self.listing_text.insert("1.0", text)
        self.db.update_generated(int(item["item_id"]), {
            "poshmark_title": result["poshmark_title"],
            "depop_title": result["depop_title"],
            "mercari_title": result["mercari_title"],
            "hashtags": result["hashtags"],
            "description": text,
        })
        self.status_var.set("PLATFORM GEN // COPY GENERATED LOCALLY")

    def mark_sold(self) -> None:
        item = self.selected()
        if item:
            self.db.mark_sold(int(item["item_id"]))
            self.refresh()
            self.status_var.set(f"INVENTORY // ITEM #{item['item_id']} MARKED SOLD")

    @staticmethod
    def money(value: object) -> str:
        try:
            return f"${float(value):,.2f}" if value is not None else "—"
        except (TypeError, ValueError):
            return "—"


def main() -> None:
    OdysseyApp().mainloop()


if __name__ == "__main__":
    main()
