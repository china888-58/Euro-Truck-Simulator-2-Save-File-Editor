"""
ETS2 / ATS 存档编辑器 — 主程序 (v2.0 生产级 UI)
==============================================
基于 Tkinter 的桌面 GUI 应用。运行：

    python main.py

打包为 EXE（Windows）：

    python build.py
"""

from __future__ import annotations

import os
import sys
from tkinter import (
    Tk, Frame, Label, StringVar,
    filedialog, messagebox, ttk, scrolledtext, BooleanVar, Toplevel
)

from sii_parser import SiiFile, SiiParseError
from editor import SaveEditor, EditResult, SKILLS, TRUCK_WEAR_PROPS

__version__ = "2.0.0"
APP_TITLE = f"欧卡 / 美卡 存档编辑器 v{__version__}"

# 配色 — 现代深色主题
BG           = "#0f0f1a"   # 主背景
BG_PANEL     = "#1a1a2e"   # 面板背景
BG_CARD      = "#1e1e2e"   # 卡片背景
BG_INPUT     = "#0a0a14"   # 输入框背景
FG           = "#e4e4e7"   # 主前景
FG_MUTED     = "#9ca3af"   # 次要文本
FG_DIM       = "#6b7280"   # 暗淡文本
ACCENT       = "#7c3aed"   # 主色(紫)
ACCENT_HOVER = "#6d28d9"
SUCCESS      = "#10b981"   # 绿
WARN         = "#f59e0b"   # 黄
ERR          = "#ef4444"   # 红
BORDER       = "#2a2a3c"   # 边框


# ============================================================
# Toast 通知系统
# ============================================================
class Toast:
    """轻量级 Toast 通知（非阻塞，右下角浮现）。"""

    def __init__(self, root: Tk):
        self.root = root
        self._after_id = None
        self._win = None

    def show(self, message: str, kind: str = "info", duration: int = 3500):
        self.hide()
        colors = {
            "info":    ("#1e293b", FG, BORDER),
            "success": ("#064e3b", SUCCESS, "#10b981"),
            "warn":    ("#78350f", WARN, "#f59e0b"),
            "err":     ("#7f1d1d", ERR, "#ef4444"),
        }
        bg, fg, border = colors.get(kind, colors["info"])

        self._win = Toplevel(self.root)
        self._win.overrideredirect(True)
        self._win.attributes("-alpha", 0.97)

        outer = Frame(self._win, bg=border)
        outer.pack()
        inner = Frame(outer, bg=bg, padx=18, pady=12)
        inner.pack(padx=1, pady=1)

        icons = {"info": "ℹ", "success": "✓", "warn": "⚠", "err": "✕"}
        icon = icons.get(kind, "ℹ")

        Label(inner, text=f"{icon}  {message}", bg=bg, fg=fg,
              font=("Microsoft YaHei UI", 10), wraplength=460,
              justify="left", anchor="w").pack()

        # 计算位置（右下角）
        self.root.update_idletasks()
        self._win.update_idletasks()
        rw = self._win.winfo_reqwidth()
        rh = self._win.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - rw - 30
        y = sh - rh - 60
        self._win.geometry(f"+{x}+{y}")

        self._after_id = self.root.after(duration, self.hide)

    def hide(self):
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


# ============================================================
# 样式初始化
# ============================================================
class StyledApp:
    """应用样式初始化与窗口配置。"""

    def __init__(self, root: Tk):
        self.root = root
        self._setup_style()
        self._setup_window()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        FONT_BASE  = ("Microsoft YaHei UI", 10)
        FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
        FONT_CARD  = ("Microsoft YaHei UI", 11, "bold")
        FONT_SMALL = ("Microsoft YaHei UI", 9)

        # 基础
        style.configure(".", background=BG, foreground=FG, font=FONT_BASE)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Card.TLabel", background=BG_CARD, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=FONT_SMALL)
        style.configure("Dim.TLabel", background=BG_CARD, foreground=FG_DIM, font=FONT_SMALL)
        style.configure("Title.TLabel", background=BG, foreground=ACCENT, font=FONT_TITLE)
        style.configure("CardTitle.TLabel", background=BG_CARD, foreground=FG, font=FONT_CARD)
        style.configure("CardHint.TLabel", background=BG_CARD, foreground=FG_MUTED, font=FONT_SMALL)
        style.configure("Status.TLabel", background=BG, foreground=FG_MUTED, font=FONT_SMALL)
        style.configure("Badge.TLabel", background=BG_PANEL, foreground=ACCENT, font=FONT_SMALL)
        style.configure("BadgeS.TLabel", background="#064e3b", foreground=SUCCESS, font=FONT_SMALL)
        style.configure("BadgeW.TLabel", background="#78350f", foreground=WARN, font=FONT_SMALL)

        # Notebook
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 6, 12, 0))
        style.configure("TNotebook.Tab",
                        background=BG_PANEL, foreground=FG_MUTED,
                        padding=(18, 10), font=FONT_BASE, borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_CARD), ("active", "#252538")],
                  foreground=[("selected", ACCENT), ("active", FG)])

        # Entry
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG,
                        insertcolor=FG, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, padding=8)
        style.map("TEntry",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)])

        # Button
        style.configure("TButton", background=ACCENT, foreground="white",
                        font=FONT_BASE, padding=(14, 8), borderwidth=0,
                        focusthickness=0)
        style.map("TButton",
                  background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
                  foreground=[("disabled", "#6b7280")])
        style.configure("Success.TButton", background=SUCCESS, foreground="white")
        style.map("Success.TButton", background=[("active", "#059669")])
        style.configure("Warn.TButton", background=WARN, foreground="white")
        style.map("Warn.TButton", background=[("active", "#d97706")])
        style.configure("Danger.TButton", background=ERR, foreground="white")
        style.map("Danger.TButton", background=[("active", "#dc2626")])
        style.configure("Ghost.TButton", background=BG_PANEL, foreground=FG)
        style.map("Ghost.TButton", background=[("active", BG_CARD)])

        # Separator
        style.configure("TSeparator", background=BORDER)

        # Checkbutton
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton",
                  background=[("active", BG)],
                  foreground=[("active", ACCENT)])

    def _setup_window(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        w, h = 1100, 760
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(960, 680)
        # 居中
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2 - 20)
        self.root.geometry(f"{w}x{h}+{x}+{y}")


# ============================================================
# 卡片容器辅助
# ============================================================
def make_card(parent, title: str = "", hint: str = "") -> ttk.Frame:
    """创建卡片容器并返回 body（内容容器）。"""
    card = ttk.Frame(parent, style="Card.TFrame", padding=16)
    card.pack(fill="x", pady=(0, 10))
    if title:
        hdr = ttk.Frame(card, style="Card.TFrame")
        hdr.pack(fill="x", pady=(0, 8))
        ttk.Label(hdr, text=title, style="CardTitle.TLabel").pack(side="left")
        if hint:
            ttk.Label(hdr, text=hint, style="CardHint.TLabel").pack(
                side="left", padx=(8, 0))
    body = ttk.Frame(card, style="Card.TFrame")
    body.pack(fill="x")
    return body


# ============================================================
# 主应用
# ============================================================
class SaveEditorApp(StyledApp):
    """主应用类。"""

    def __init__(self, root: Tk):
        super().__init__(root)
        self.sii: SiiFile | None = None
        self.editor: SaveEditor | None = None
        self.current_path: str | None = None
        self._auto_backup = BooleanVar(value=True)
        self.toast = Toast(root)

        self._build_ui()
        self._set_status("就绪。请通过「打开存档」加载 .sii 文件。", "info")

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self):
        # ----- 顶栏 -----
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=16, pady=(14, 8))

        hdr_left = ttk.Frame(top)
        hdr_left.pack(side="left")
        ttk.Label(hdr_left, text="🚛", font=("Segoe UI Emoji", 22)).pack(side="left")
        title_box = ttk.Frame(hdr_left)
        title_box.pack(side="left", padx=(10, 0))
        ttk.Label(title_box, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Euro Truck Simulator 2 / American Truck Simulator",
                  style="Muted.TLabel").pack(anchor="w")

        btns = ttk.Frame(top)
        btns.pack(side="right")
        self.btn_open = ttk.Button(btns, text="📂 打开存档", command=self.on_open)
        self.btn_open.pack(side="left", padx=4)
        self.btn_save = ttk.Button(btns, text="💾 保存", style="Success.TButton",
                                   command=self.on_save, state="disabled")
        self.btn_save.pack(side="left", padx=4)
        self.btn_saveas = ttk.Button(btns, text="📥 另存为", style="Ghost.TButton",
                                     command=self.on_save_as, state="disabled")
        self.btn_saveas.pack(side="left", padx=4)

        # ----- 路径栏 -----
        path_bar = ttk.Frame(self.root)
        path_bar.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Label(path_bar, text="📁", style="Muted.TLabel").pack(side="left")
        self.path_var = StringVar(value="未加载存档")
        ttk.Label(path_bar, textvariable=self.path_var, style="Muted.TLabel").pack(
            side="left", padx=(6, 12))
        self.fmt_badge_var = StringVar(value="")
        ttk.Label(path_bar, textvariable=self.fmt_badge_var,
                  style="Badge.TLabel").pack(side="left")

        # ----- 主区域 Notebook -----
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.tab_overview = self._make_tab("📋 概述")
        self.tab_money    = self._make_tab("💰 金钱 / 贷款")
        self.tab_xp       = self._make_tab("⭐ 经验 / 技能")
        self.tab_truck    = self._make_tab("🚛 卡车 / 燃油")
        self.tab_map      = self._make_tab("🗺️ 地图 / 公司")

        self._build_overview_tab(self.tab_overview)
        self._build_money_tab(self.tab_money)
        self._build_xp_tab(self.tab_xp)
        self._build_truck_tab(self.tab_truck)
        self._build_map_tab(self.tab_map)

        # ----- 底栏 -----
        bot = ttk.Frame(self.root)
        bot.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Separator(bot).pack(fill="x", pady=(0, 8))
        bot_inner = ttk.Frame(bot)
        bot_inner.pack(fill="x")
        self.status_dot = Label(bot_inner, text="●", bg=BG, fg=FG_MUTED,
                                 font=("Segoe UI", 12))
        self.status_dot.pack(side="left")
        self.status_var = StringVar(value="")
        ttk.Label(bot_inner, textvariable=self.status_var, style="Status.TLabel").pack(
            side="left", padx=(8, 12))
        ttk.Label(bot_inner, text="保存前自动备份", style="Muted.TLabel").pack(side="right")
        ttk.Checkbutton(bot_inner, variable=self._auto_backup).pack(side="right")

    def _make_tab(self, title: str) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text=title)
        return f

    # ---- 概述 ----
    def _build_overview_tab(self, parent):
        body = make_card(parent, "存档概述", "加载存档后显示关键信息")
        self.overview_text = scrolledtext.ScrolledText(
            body, height=26, wrap="word",
            bg=BG_INPUT, fg=FG, insertbackground=FG,
            font=("Consolas", 11), borderwidth=0, relief="flat",
            padx=12, pady=10)
        self.overview_text.pack(fill="both", expand=True)
        self.overview_text.configure(state="disabled")

        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(8, 0))
        self.btn_refresh = ttk.Button(bf, text="🔄 刷新概述", command=self.refresh_overview,
                                       state="disabled")
        self.btn_refresh.pack(side="left")

    # ---- 金钱 / 贷款 ----
    def _build_money_tab(self, parent):
        body = make_card(parent, "金钱与贷款", "直接修改现金账户与银行贷款")

        self.money_var = StringVar()
        self.bank_var = StringVar()
        self.loan_var = StringVar()
        self.limit_var = StringVar()

        rows = [
            ("💰 现金账户", "money_account", self.money_var,
             "玩家当前可用的现金"),
            ("🏦 银行存款", "bank_money", self.bank_var,
             "存入银行的资金（部分存档有）"),
            ("📉 贷款余额", "loan_amount", self.loan_var,
             "尚未偿还的贷款；置 0 即「还清贷款」"),
            ("📊 贷款上限", "player_money_limit", self.limit_var,
             "可申请的最大贷款额度"),
        ]
        for label, field, var, hint in rows:
            self._build_input_row(body, label, field, var, hint)

        # 快捷预设
        preset_frame = ttk.Frame(body, style="Card.TFrame")
        preset_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(preset_frame, text="快捷预设：", style="CardHint.TLabel").pack(
            anchor="w", pady=(0, 4))
        btn_row = ttk.Frame(preset_frame, style="Card.TFrame")
        btn_row.pack(fill="x")
        for label, val in [("1 千万", 10_000_000),
                          ("1 亿", 100_000_000),
                          ("10 亿", 1_000_000_000),
                          ("999 亿", 99_999_999_999)]:
            ttk.Button(btn_row, text=label, style="Ghost.TButton",
                       command=lambda v=val: self._apply_money_preset(v)).pack(
                side="left", padx=(0, 6))

        bf = ttk.Frame(body, style="Card.TFrame")
        bf.pack(fill="x", pady=(12, 0))
        ttk.Button(bf, text="✓ 应用金钱修改", style="Success.TButton",
                   command=self.apply_money).pack(side="left")
        ttk.Button(bf, text="还清贷款", style="Warn.TButton",
                   command=self.pay_off_loan).pack(side="left", padx=8)

    # ---- 经验 / 技能 ----
    def _build_xp_tab(self, parent):
        body = make_card(parent, "等级与经验", "")

        self.level_var = StringVar()
        self.xp_var = StringVar()
        self._build_input_row(body, "⭐ 等级", "player_level", self.level_var,
                              "玩家等级（整数，建议 0 ~ 200）")
        self._build_input_row(body, "✨ 经验值", "player_xp", self.xp_var,
                              "玩家经验值（建议与等级匹配）")

        bf = ttk.Frame(body, style="Card.TFrame")
        bf.pack(fill="x", pady=(8, 0))
        ttk.Label(bf, text="等级快捷：", style="CardHint.TLabel").pack(side="left")
        for label, lv in [("Lv.1", 1), ("Lv.50", 50), ("Lv.100", 100), ("Lv.200", 200)]:
            ttk.Button(bf, text=label, style="Ghost.TButton",
                       command=lambda l=lv: self._apply_level_preset(l)).pack(
                side="left", padx=(6, 0))

        skill_body = make_card(parent, "技能", "0 ~ 6 级，6 为满级")
        self.skill_vars = {}
        for prop, cn, _ in SKILLS:
            v = StringVar()
            self._build_input_row(skill_body, f"  {cn}", prop, v, "")
            self.skill_vars[prop] = v

        bf2 = ttk.Frame(skill_body, style="Card.TFrame")
        bf2.pack(fill="x", pady=(12, 0))
        ttk.Button(bf2, text="✓ 应用等级与经验", style="Success.TButton",
                   command=self.apply_xp_level).pack(side="left")
        ttk.Button(bf2, text="全部技能满级", style="Warn.TButton",
                   command=self.max_skills).pack(side="left", padx=8)

    # ---- 卡车 ----
    def _build_truck_tab(self, parent):
        body = make_card(parent, "卡车信息", "修改玩家当前驾驶的卡车（自动追踪 assigned_truck）")

        self.truck_info_var = StringVar(value="未加载")
        ttk.Label(body, textvariable=self.truck_info_var,
                  style="CardHint.TLabel").pack(anchor="w", pady=(0, 12))

        self.fuel_var = StringVar()
        self.fuel_cap_var = StringVar()
        self.odo_var = StringVar()
        self._build_input_row(body, "⛽ 燃油", "fuel", self.fuel_var, "当前油量（升）或百分比")
        self._build_input_row(body, "🛢️ 油箱容量", "fuel_capacity",
                              self.fuel_cap_var, "可设更大油箱")
        self._build_input_row(body, "📏 里程表", "odometer", self.odo_var,
                              "总行驶里程（公里）")

        bf = ttk.Frame(body, style="Card.TFrame")
        bf.pack(fill="x", pady=(12, 0))
        ttk.Button(bf, text="✓ 应用卡车修改", style="Success.TButton",
                   command=self.apply_truck).pack(side="left")
        ttk.Button(bf, text="🛢️ 加满燃油", style="Warn.TButton",
                   command=self.full_fuel).pack(side="left", padx=8)
        ttk.Button(bf, text="🔧 修复全车", style="Warn.TButton",
                   command=self.repair_truck).pack(side="left", padx=4)
        ttk.Button(bf, text="🔧 清零永久磨损", style="Warn.TButton",
                   command=self.repair_truck_permanent).pack(side="left", padx=4)

        # 磨损卡片 — 明确说明车轮显示为各轮最大值
        wear_body = make_card(parent, "磨损部件",
                              "0 = 全新；1 = 完全损坏。车轮显示为各轮最大磨损值")
        self.wear_vars = {}
        for prop, cn in TRUCK_WEAR_PROPS:
            v = StringVar()
            self._build_input_row(wear_body, f"🔧 {cn}", prop, v, "")
            self.wear_vars[prop] = v

        # 车牌号卡片
        plate_body = make_card(parent, "车牌号", "纯文本车牌，保留原 UI 标记")
        self.plate_var = StringVar()
        self._build_input_row(plate_body, "🏷️ 车牌号", "license_plate", self.plate_var,
                              "如 AB-123-CD")
        bf_plate = ttk.Frame(plate_body, style="Card.TFrame")
        bf_plate.pack(fill="x", pady=(8, 0))
        ttk.Button(bf_plate, text="✓ 应用车牌", style="Success.TButton",
                   command=self.apply_license_plate).pack(side="left")

    # ---- 地图 / 公司 ----
    def _build_map_tab(self, parent):
        body = make_card(parent, "地图与公司", "一键解锁全图公司、车库、城市等")

        self.map_info_var = StringVar(value="未加载")
        ttk.Label(body, textvariable=self.map_info_var,
                  style="CardHint.TLabel").pack(anchor="w", pady=(0, 12))

        actions = [
            ("🌍 解锁全部公司", "discovered=true",
             "将所有 company 单元标记为已发现。",
             self.discover_all),
            ("🏠 解锁全部车库", "status=bought",
             "将所有 garage 单元设置为已购买状态。",
             self.unlock_garages),
            ("👥 提升司机招募上限到 100", "recruit_limit=100",
             "将 recruit/driver_limit 字段提升到 100。",
             self.increase_recruit_limit),
            ("⭐ AI 司机满技能 + ADR 全开", "skills=6, adr=63",
             "把所有 driver_ai 的 5 项技能设为 6.0、ADR 设为 63。",
             self.max_driver_skills),
            ("🚛 修复所有挂车磨损", "wear=0",
             "把所有 trailer 单元的磨损 + 永久磨损 + 货物损坏归零。",
             self.repair_all_trailers),
            ("⏰ 延长任务期限 +72 小时", "expiration_time+=72h",
             "把所有 job_offer_data 的 expiration_time 延长 72 小时。",
             self.extend_jobs),
        ]
        for title, badge, desc, cmd in actions:
            row = ttk.Frame(body, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            left = ttk.Frame(row, style="Card.TFrame")
            left.pack(side="left", fill="x", expand=True)
            title_row = ttk.Frame(left, style="Card.TFrame")
            title_row.pack(fill="x")
            ttk.Label(title_row, text=title, style="Card.TLabel",
                      font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
            ttk.Label(title_row, text=badge, style="Badge.TLabel").pack(
                side="left", padx=(8, 0))
            ttk.Label(left, text=desc, style="CardHint.TLabel").pack(
                anchor="w", pady=(2, 0))
            ttk.Button(row, text="执行", style="Warn.TButton",
                       command=cmd).pack(side="right", padx=(8, 0))

    # ---- 通用行 ----
    def _build_input_row(self, parent, label, field, var, hint):
        f = ttk.Frame(parent, style="Card.TFrame")
        f.pack(fill="x", pady=3)
        ttk.Label(f, text=label, style="Card.TLabel", width=18, anchor="w").pack(side="left")
        ttk.Entry(f, textvariable=var, width=24).pack(side="left", padx=(8, 12))
        if field:
            ttk.Label(f, text=f"({field})", style="Dim.TLabel").pack(side="left")
        if hint:
            ttk.Label(f, text="  " + hint, style="CardHint.TLabel").pack(side="left")

    # ============================================================
    # 状态 / 通知
    # ============================================================
    def _set_status(self, text: str, kind: str = "info"):
        self.status_var.set(text)
        color = {"info": FG_MUTED, "success": SUCCESS,
                 "warn": WARN, "err": ERR}.get(kind, FG_MUTED)
        try:
            self.status_dot.config(fg=color)
        except Exception:
            pass

    # ============================================================
    # 文件操作
    # ============================================================
    def on_open(self):
        path = filedialog.askopenfilename(
            title="选择 ETS2 / ATS 存档 (.sii)",
            filetypes=[("SII 存档", "*.sii"), ("所有文件", "*.*")],
            initialdir=self._default_save_dir(),
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        try:
            self.sii = SiiFile.load(path)
            self.editor = SaveEditor(self.sii)
            self.current_path = path
            self.path_var.set(path)
            self.fmt_badge_var.set(f" {self._fmt_label()} ")
            self._populate_tabs()
            self.btn_save.config(state="normal")
            self.btn_saveas.config(state="normal")
            self.btn_refresh.config(state="normal")
            self._set_status(f"已加载: {os.path.basename(path)}", "success")
            self.toast.show(f"已加载存档: {os.path.basename(path)}", "success")
        except SiiParseError as e:
            self._set_status(f"解析失败: {e}", "err")
            self.toast.show(f"解析失败: {e}", "err", duration=5000)
        except Exception as e:
            self._set_status(f"加载失败: {e}", "err")
            self.toast.show(f"加载失败: {e}", "err", duration=5000)

    def on_save(self):
        if not self.sii:
            return
        if not self.sii.is_dirty():
            self._set_status("存档未做任何修改。", "info")
            self.toast.show("你没有修改任何内容。", "info")
            return
        if self._auto_backup.get():
            try:
                bk = self.sii.backup(self.current_path)
                self._set_status(f"已自动备份: {os.path.basename(bk)}", "info")
            except Exception as e:
                if not messagebox.askyesno("备份失败",
                        f"自动备份失败：{e}\n是否仍然继续保存?"):
                    return
        try:
            self.sii.save(self.current_path, binary=None)
            self._set_status(f"已保存: {os.path.basename(self.current_path)}", "success")
            self.toast.show("存档已保存。建议先退出游戏再启动,以避免冲突。", "success")
            # 关键：保存后重新加载文件并刷新 UI（解决显示旧数据的问题）
            self._reload_after_save()
        except Exception as e:
            self._set_status(f"保存失败: {e}", "err")
            self.toast.show(f"保存失败: {e}", "err", duration=5000)

    def _reload_after_save(self):
        """保存后重新加载文件并刷新 UI 显示。"""
        if not self.current_path:
            return
        try:
            self.sii = SiiFile.load(self.current_path)
            self.editor = SaveEditor(self.sii)
            self._populate_tabs()
        except Exception as e:
            self._set_status(f"刷新显示失败: {e}", "warn")

    def on_save_as(self):
        if not self.sii:
            return
        path = filedialog.asksaveasfilename(
            title="另存为",
            defaultextension=".sii",
            filetypes=[("SII 存档", "*.sii"), ("所有文件", "*.*")],
            initialfile="game_edited.sii",
        )
        if not path:
            return

        is_bsii = self.sii._bsii is not None
        if is_bsii:
            choice = messagebox.askyesnocancel(
                "选择保存格式",
                f"原存档格式: {self._fmt_label()}\n\n"
                "BSII 二进制结构必须保留,只可选是否加密:\n\n"
                "是 = ScsC 加密 BSII (ETS2 1.6 默认,推荐)\n"
                "否 = 明文 BSII (无加密,便于调试)\n"
                "取消 = 放弃"
            )
            if choice is None:
                return
            try:
                self.sii.save(path, encrypted=bool(choice))
                self._set_status(f"已另存为: {os.path.basename(path)}", "success")
                self.toast.show(f"已另存为:\n{path}", "success")
            except Exception as e:
                self._set_status(f"保存失败: {e}", "err")
                self.toast.show(f"保存失败: {e}", "err", duration=5000)
            return

        choice = messagebox.askyesnocancel(
            "选择保存格式",
            f"原存档格式: {self._fmt_label()}\n\n"
            "是 = ScsC 加密格式（ETS2 1.5+ / ATS 新版默认，推荐）\n"
            "否 = 明文文本格式（便于二次编辑，游戏需 g_save_format=2）\n"
            "取消 = 放弃"
        )
        if choice is None:
            return
        try:
            self.sii.save(path, encrypted=bool(choice), binary=False)
            self._set_status(f"已另存为: {os.path.basename(path)}", "success")
            self.toast.show(f"已另存为:\n{path}", "success")
        except Exception as e:
            self._set_status(f"保存失败: {e}", "err")
            self.toast.show(f"保存失败: {e}", "err", duration=5000)

    def _fmt_label(self) -> str:
        if not self.sii:
            return "未加载"
        if self.sii._bsii is not None:
            if self.sii._encrypted:
                return "BSII + ScsC 加密"
            return "BSII 二进制 (明文)"
        if self.sii._encrypted:
            return "ScsC 加密"
        if self.sii._binary:
            return "zlib 二进制"
        return "明文文本"

    def _default_save_dir(self):
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Documents", "Euro Truck Simulator 2", "profiles"),
            os.path.join(home, "Documents", "American Truck Simulator", "profiles"),
            home,
        ]
        for c in candidates:
            if os.path.isdir(c):
                return c
        return home

    # ============================================================
    # 加载后填充 UI
    # ============================================================
    def _populate_tabs(self):
        ed = self.editor
        if ed is None:
            return

        # 金钱
        self.money_var.set(str(ed.get_money()))
        self.bank_var.set(str(ed.get_bank_money()))
        self.loan_var.set(str(ed.get_loan()))
        limit = self.sii.get_property(self.editor.economy_unit_name, "player_money_limit", "0")
        self.limit_var.set(str(limit).strip().strip('"'))

        # XP / 等级 / 技能
        self.level_var.set(str(ed.get_level()))
        self.xp_var.set(str(ed.get_xp()))
        for prop, _, _ in SKILLS:
            self.skill_vars[prop].set(f"{ed.get_skill(prop):.1f}")

        # 卡车
        info = ed.get_truck_info()
        if info["found"]:
            brand_model = f"{info['brand']} {info['model']}".strip()
            if not brand_model and info.get("license_plate"):
                brand_model = f"车牌: {info['license_plate']}"
            elif not brand_model:
                brand_model = "(无品牌型号信息)"
            self.truck_info_var.set(
                f"卡车实例: {info['instance']}   {brand_model}")
            if info["fuel_is_relative"]:
                self.fuel_var.set(f"{info['fuel']*100:.1f}%")
            else:
                self.fuel_var.set(f"{info['fuel']:.1f}")
            self.fuel_cap_var.set(f"{info['fuel_capacity']:.1f}")
            self.odo_var.set(f"{info['odometer']:.1f}")
            for prop, _ in TRUCK_WEAR_PROPS:
                if prop in info:
                    self.wear_vars[prop].set(f"{info[prop]:.4f}")
                else:
                    self.wear_vars[prop].set("0.0000")
            self.plate_var.set(info.get("license_plate", ""))
        else:
            self.truck_info_var.set("未找到玩家当前卡车单元")

        # 地图
        companies = ed.list_companies()
        if companies:
            discovered = sum(1 for c in companies if
                self.sii.get_property(c.instance_name, "discovered", "false") == "true")
            self.map_info_var.set(
                f"共 {len(companies)} 家公司,其中 {discovered} 家已发现")
        else:
            self.map_info_var.set("未找到 company 单元")

        # 概述
        self.refresh_overview()

        # 启用按钮
        for child in self.nb.winfo_children():
            for c in child.winfo_children():
                self._enable_all(c)

    def _enable_all(self, widget):
        try:
            if widget.winfo_class() == "TButton" and str(widget.cget("state")) == "disabled":
                widget.config(state="normal")
        except Exception:
            pass
        for c in widget.winfo_children():
            self._enable_all(c)

    # ============================================================
    # 操作回调
    # ============================================================
    def refresh_overview(self):
        if not self.editor:
            return
        text = self.editor.summary()
        self.overview_text.configure(state="normal")
        self.overview_text.delete("1.0", "end")
        self.overview_text.insert("1.0", text)
        self.overview_text.configure(state="disabled")

    def _parse_int(self, s: str) -> int | None:
        s = s.strip().replace(",", "")
        try:
            return int(float(s))
        except ValueError:
            return None

    def _parse_float(self, s: str) -> float | None:
        s = s.strip().replace(",", "").rstrip("fF")
        # 支持百分比输入（fuel_relative 字段）
        if s.endswith("%"):
            try:
                return float(s[:-1]) / 100.0
            except ValueError:
                return None
        try:
            return float(s)
        except ValueError:
            return None

    def apply_money(self):
        if not self.editor:
            return
        changed = 0
        msg = []

        money = self._parse_int(self.money_var.get())
        if money is not None:
            r = self.editor.set_money(money)
            if r.success: changed += 1; msg.append(r.message)
        else:
            self.toast.show("现金账户必须是数字", "err")
            return

        bank = self._parse_int(self.bank_var.get())
        if bank is not None:
            r = self.editor.set_bank_money(bank)
            if r.success: changed += 1; msg.append(r.message)

        loan = self._parse_int(self.loan_var.get())
        if loan is not None:
            r = self.editor.set_loan(loan)
            if r.success: changed += 1; msg.append(r.message)

        limit = self._parse_int(self.limit_var.get())
        if limit is not None:
            r = self.editor.set_loan_limit(limit)
            if r.success: changed += 1; msg.append(r.message)

        self._populate_tabs()
        self._after_edit(f"已修改 {changed} 项金钱/贷款字段", msg)

    def _apply_money_preset(self, amount):
        if not self.editor:
            return
        self.money_var.set(str(amount))
        r = self.editor.set_money(amount)
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def pay_off_loan(self):
        if not self.editor:
            return
        r = self.editor.pay_off_loan()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def apply_xp_level(self):
        if not self.editor:
            return
        msg = []
        lv = self._parse_int(self.level_var.get())
        if lv is not None:
            r = self.editor.set_level(lv)
            if r.success: msg.append(r.message)
        else:
            self.toast.show("等级必须是整数", "err")
            return

        xp = self._parse_int(self.xp_var.get())
        if xp is not None:
            r = self.editor.set_xp(xp)
            if r.success: msg.append(r.message)

        for prop, _, _ in SKILLS:
            v = self._parse_float(self.skill_vars[prop].get())
            if v is not None:
                r = self.editor.set_skill(prop, v)
                if r.success: msg.append(r.message)

        self._populate_tabs()
        self._after_edit("等级 / 经验 / 技能已应用", msg)

    def _apply_level_preset(self, level):
        if not self.editor:
            return
        self.level_var.set(str(level))
        xp = max(0, level * level * 1500)
        self.xp_var.set(str(xp))
        r1 = self.editor.set_level(level)
        r2 = self.editor.set_xp(xp)
        self._populate_tabs()
        self._after_edit(f"已设置等级为 Lv.{level}（估算 XP={xp:,}）",
                         [r1.message, r2.message])

    def max_skills(self):
        if not self.editor:
            return
        r = self.editor.max_all_skills()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def apply_truck(self):
        if not self.editor:
            return
        msg = []

        fuel = self._parse_float(self.fuel_var.get())
        if fuel is not None:
            r = self.editor.set_fuel(fuel)
            if r.success: msg.append(r.message)

        cap = self._parse_float(self.fuel_cap_var.get())
        if cap is not None:
            r = self.editor.set_truck_prop("fuel_capacity", cap)
            if r.success: msg.append(r.message)

        odo = self._parse_float(self.odo_var.get())
        if odo is not None:
            r = self.editor.set_odometer(odo)
            if r.success: msg.append(r.message)

        for prop, _ in TRUCK_WEAR_PROPS:
            v = self._parse_float(self.wear_vars[prop].get())
            if v is not None:
                v = max(0.0, min(1.0, v))
                r = self.editor.set_truck_prop(prop, v)
                if r.success: msg.append(r.message)

        # 关键：刷新 UI 显示当前实际值（解决磨损显示旧值的问题）
        self._populate_tabs()
        self._after_edit("卡车参数已应用", msg)

    def full_fuel(self):
        if not self.editor:
            return
        r = self.editor.full_fuel()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def repair_truck(self):
        if not self.editor:
            return
        r = self.editor.repair_truck()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def discover_all(self):
        if not self.editor:
            return
        r = self.editor.discover_all_companies()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def unlock_garages(self):
        if not self.editor:
            return
        r = self.editor.unlock_all_garages()
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def increase_recruit_limit(self):
        if not self.editor:
            return
        r = self.editor.set_recruit_limit(100)
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def max_driver_skills(self):
        if not self.editor:
            return
        r = self.editor.max_driver_skills()
        self._after_edit(r.message, [r.message])

    def repair_all_trailers(self):
        if not self.editor:
            return
        r = self.editor.repair_trailers()
        self._after_edit(r.message, [r.message])

    def extend_jobs(self):
        if not self.editor:
            return
        r = self.editor.extend_job_offers(hours=72)
        self._after_edit(r.message, [r.message])

    def repair_truck_permanent(self):
        if not self.editor:
            return
        r = self.editor.repair_truck_permanent()
        # 关键：刷新磨损显示（永久磨损清零后立即更新）
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def apply_license_plate(self):
        if not self.editor:
            return
        plate = self.plate_var.get().strip()
        if not plate:
            self.toast.show("车牌号不能为空", "err")
            return
        r = self.editor.set_truck_license_plate(plate)
        self._populate_tabs()
        self._after_edit(r.message, [r.message])

    def _after_edit(self, summary: str, details: list):
        if details:
            self._set_status(summary, "success")
            self.toast.show("\n".join(details), "success")
        else:
            self._set_status(summary, "warn")
            self.toast.show(summary, "warn")
        self.refresh_overview()


def main():
    root = Tk()
    app = SaveEditorApp(root)
    # 支持命令行参数加载
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(100, lambda: app._load_file(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
