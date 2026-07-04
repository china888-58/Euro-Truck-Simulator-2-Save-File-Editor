"""
ETS2 / ATS 存档编辑器 — 主程序
====================================
基于 Tkinter 的桌面 GUI 应用。运行：

    python main.py

打包为 EXE（Windows）：

    python build.py          # 见 build.py
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from tkinter import (
    Tk, Frame, Label, Button, Entry, StringVar, IntVar, DoubleVar,
    filedialog, messagebox, ttk, scrolledtext, BooleanVar
)

from sii_parser import SiiFile, SiiParseError
from editor import SaveEditor, EditResult, SKILLS, TRUCK_WEAR_PROPS

__version__ = "1.0.0"
APP_TITLE = f"欧卡 / 美卡 存档编辑器 v{__version__}"

# 配色
BG = "#1e1e2e"
BG_PANEL = "#2a2a3c"
FG = "#e4e4e7"
ACCENT = "#7c3aed"
ACCENT_HOVER = "#6d28d9"
SUCCESS = "#10b981"
WARN = "#f59e0b"
ERR = "#ef4444"


class StyledApp:
    """应用样式初始化与公共工具方法。"""

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

        # 基础颜色
        style.configure(".", background=BG, foreground=FG, font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)
        style.configure("Title.TLabel", background=BG, foreground=ACCENT,
                        font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground="#a5b4fc",
                        font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Status.TLabel", background=BG, foreground="#9ca3af",
                        font=("Microsoft YaHei UI", 9))

        # Notebook（标签页）
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=BG_PANEL, foreground=FG,
                        padding=(16, 8), font=("Microsoft YaHei UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

        # 输入框
        style.configure("TEntry", fieldbackground="#0f0f1a", foreground=FG,
                        insertcolor=FG, bordercolor=ACCENT, lightcolor=ACCENT)
        style.map("TEntry", bordercolor=[("focus", ACCENT_HOVER)])

        # 按钮
        style.configure("TButton", background=ACCENT, foreground="white",
                        font=("Microsoft YaHei UI", 10, "bold"),
                        padding=(12, 6), borderwidth=0)
        style.map("TButton",
                  background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)])
        style.configure("Success.TButton", background=SUCCESS, foreground="white")
        style.map("Success.TButton", background=[("active", "#059669")])
        style.configure("Warn.TButton", background=WARN, foreground="white")
        style.map("Warn.TButton", background=[("active", "#d97706")])
        style.configure("Ghost.TButton", background=BG_PANEL, foreground=FG)
        style.map("Ghost.TButton", background=[("active", "#3a3a4c")])

        # 滚动文本框
        style.configure("TScrolledText", background="#0f0f1a", foreground=FG)

    def _setup_window(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        w, h = 900, 680
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(w, h)
        # 居中
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2 - 30)
        self.root.geometry(f"{w}x{h}+{x}+{y}")


class SaveEditorApp(StyledApp):
    """主应用类。"""

    def __init__(self, root: Tk):
        super().__init__(root)
        self.sii: SiiFile | None = None
        self.editor: SaveEditor | None = None
        self.current_path: str | None = None
        self._auto_backup = BooleanVar(value=True)

        self._build_ui()
        self._set_status("就绪。请通过「打开存档」加载 .sii 文件。")

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self):
        # 顶栏
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(top, text="🚛 " + APP_TITLE, style="Title.TLabel").pack(side="left")

        self.path_var = StringVar(value="未加载存档")
        ttk.Label(top, textvariable=self.path_var, style="Status.TLabel").pack(
            side="left", padx=(16, 0))

        # 顶栏按钮
        btns = ttk.Frame(top)
        btns.pack(side="right")
        self.btn_open = ttk.Button(btns, text="📂 打开存档", command=self.on_open)
        self.btn_open.pack(side="left", padx=4)
        self.btn_save = ttk.Button(btns, text="💾 保存", style="Success.TButton",
                                   command=self.on_save, state="disabled")
        self.btn_save.pack(side="left", padx=4)
        self.btn_saveas = ttk.Button(btns, text="💾 另存为", style="Ghost.TButton",
                                     command=self.on_save_as, state="disabled")
        self.btn_saveas.pack(side="left", padx=4)

        # 主区域 Notebook
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=6)

        self.tab_overview = self._make_tab("📋 概述")
        self.tab_money = self._make_tab("💰 金钱 / 贷款")
        self.tab_xp = self._make_tab("⭐ 经验 / 技能")
        self.tab_truck = self._make_tab("🚛 卡车 / 燃油")
        self.tab_map = self._make_tab("🗺️ 地图 / 公司")

        self._build_overview_tab(self.tab_overview)
        self._build_money_tab(self.tab_money)
        self._build_xp_tab(self.tab_xp)
        self._build_truck_tab(self.tab_truck)
        self._build_map_tab(self.tab_map)

        # 底栏
        bot = ttk.Frame(self.root)
        bot.pack(fill="x", padx=12, pady=(6, 12))
        self.status_var = StringVar(value="")
        ttk.Label(bot, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Checkbutton(bot, text="保存前自动备份",
                        variable=self._auto_backup,
                        style="Ghost.TButton").pack(side="right")

    def _make_tab(self, title) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text=title)
        return f

    # ---- 概述 ----
    def _build_overview_tab(self, parent):
        ttk.Label(parent, text="存档概述", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="加载存档后，这里将显示当前存档的关键信息。",
                  style="Status.TLabel").pack(anchor="w", pady=(4, 12))

        self.overview_text = scrolledtext.ScrolledText(
            parent, height=22, wrap="word",
            bg="#0f0f1a", fg=FG, insertbackground=FG,
            font=("Consolas", 11), borderwidth=0, relief="flat")
        self.overview_text.pack(fill="both", expand=True)
        self.overview_text.configure(state="disabled")

        # 底部按钮
        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(8, 0))
        ttk.Button(bf, text="🔄 刷新概述", command=self.refresh_overview,
                   state="disabled").pack(side="left")

    # ---- 金钱 / 贷款 ----
    def _build_money_tab(self, parent):
        ttk.Label(parent, text="金钱与贷款", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="直接修改现金账户与银行贷款。",
                  style="Status.TLabel").pack(anchor="w", pady=(4, 12))

        self.money_var = StringVar()
        self.bank_var = StringVar()
        self.loan_var = StringVar()
        self.limit_var = StringVar()

        rows = [
            ("💰 现金账户 (money_account)", self.money_var,
             "玩家当前可用的现金"),
            ("🏦 银行存款 (bank_money)", self.bank_var,
             "存入银行的资金（部分存档有）"),
            ("📉 贷款余额 (loan_amount)", self.loan_var,
             "尚未偿还的贷款；置 0 即「还清贷款」"),
            ("📊 贷款上限 (player_money_limit)", self.limit_var,
             "可申请的最大贷款额度"),
        ]
        for label, var, hint in rows:
            self._build_input_row(parent, label, var, hint)

        # 预设按钮
        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Label(parent, text="快捷预设", style="Status.TLabel").pack(anchor="w", pady=(0, 6))
        preset_frame = ttk.Frame(parent)
        preset_frame.pack(fill="x")
        for label, val in [("1 千万", 10_000_000),
                          ("1 亿", 100_000_000),
                          ("10 亿", 1_000_000_000),
                          ("999 亿", 99_999_999_999)]:
            ttk.Button(preset_frame, text=label, style="Ghost.TButton",
                       command=lambda v=val: self._apply_money_preset(v)).pack(
                side="left", padx=(0, 6))

        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(12, 0))
        ttk.Button(bf, text="✓ 应用金钱修改", style="Success.TButton",
                   command=self.apply_money).pack(side="left")
        ttk.Button(bf, text="还清贷款", style="Warn.TButton",
                   command=self.pay_off_loan).pack(side="left", padx=8)

    # ---- 经验 / 技能 ----
    def _build_xp_tab(self, parent):
        ttk.Label(parent, text="经验与技能", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="修改玩家等级、经验值与 5 项技能等级。",
                  style="Status.TLabel").pack(anchor="w", pady=(4, 12))

        self.level_var = StringVar()
        self.xp_var = StringVar()
        self._build_input_row(parent, "⭐ 等级 (player_level)", self.level_var,
                              "玩家等级（整数，建议 0 ~ 200）")
        self._build_input_row(parent, "✨ 经验值 (player_xp)", self.xp_var,
                              "玩家经验值（建议与等级匹配）")

        # 等级预设
        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(8, 0))
        ttk.Label(bf, text="等级快捷：", style="Status.TLabel").pack(side="left")
        for label, lv in [("Lv.1", 1), ("Lv.50", 50), ("Lv.100", 100), ("Lv.200", 200)]:
            ttk.Button(bf, text=label, style="Ghost.TButton",
                       command=lambda l=lv: self._apply_level_preset(l)).pack(
                side="left", padx=(6, 0))

        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Label(parent, text="技能（0 ~ 6 级，6 为满级）", style="Subtitle.TLabel").pack(anchor="w")

        self.skill_vars = {}
        for prop, cn, _ in SKILLS:
            v = StringVar()
            self._build_input_row(parent, f"  {cn}", v, "")
            self.skill_vars[prop] = v

        bf2 = ttk.Frame(parent)
        bf2.pack(fill="x", pady=(12, 0))
        ttk.Button(bf2, text="✓ 应用等级与经验", style="Success.TButton",
                   command=self.apply_xp_level).pack(side="left")
        ttk.Button(bf2, text="全部技能满级", style="Warn.TButton",
                   command=self.max_skills).pack(side="left", padx=8)

    # ---- 卡车 ----
    def _build_truck_tab(self, parent):
        ttk.Label(parent, text="卡车与挂车", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="修改玩家当前驾驶的卡车参数（自动追踪 assigned_truck）。",
                  style="Status.TLabel").pack(anchor="w", pady=(4, 12))

        self.truck_info_var = StringVar(value="未加载")
        ttk.Label(parent, textvariable=self.truck_info_var,
                  style="Status.TLabel").pack(anchor="w", pady=(0, 12))

        self.fuel_var = StringVar()
        self.fuel_cap_var = StringVar()
        self.odo_var = StringVar()
        self._build_input_row(parent, "⛽ 燃油 (fuel)", self.fuel_var, "当前油量（升）")
        self._build_input_row(parent, "🛢️ 油箱容量 (fuel_capacity)",
                              self.fuel_cap_var, "可设更大油箱")
        self._build_input_row(parent, "📏 里程表 (odometer)", self.odo_var, "总行驶里程（公里）")

        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Label(parent, text="磨损部件（0 = 全新；1 = 完全损坏）",
                  style="Subtitle.TLabel").pack(anchor="w")
        self.wear_vars = {}
        for prop, cn in TRUCK_WEAR_PROPS:
            v = StringVar()
            self._build_input_row(parent, f"  🔧 {cn}", v, "")
            self.wear_vars[prop] = v

        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(12, 0))
        ttk.Button(bf, text="✓ 应用卡车修改", style="Success.TButton",
                   command=self.apply_truck).pack(side="left")
        ttk.Button(bf, text="🛢️ 加满燃油", style="Warn.TButton",
                   command=self.full_fuel).pack(side="left", padx=8)
        ttk.Button(bf, text="🔧 修复全车", style="Warn.TButton",
                   command=self.repair_truck).pack(side="left", padx=4)
        ttk.Button(bf, text="🔧 清零永久磨损", style="Warn.TButton",
                   command=self.repair_truck_permanent).pack(side="left", padx=4)

        # 车牌号修改
        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Label(parent, text="车牌号 (license_plate)",
                  style="Subtitle.TLabel").pack(anchor="w")
        self.plate_var = StringVar()
        self._build_input_row(parent, "🏷️ 车牌号", self.plate_var,
                              "纯文本车牌(如 AB-123-CD),保留原 UI 标记")
        bf_plate = ttk.Frame(parent)
        bf_plate.pack(fill="x", pady=(8, 0))
        ttk.Button(bf_plate, text="✓ 应用车牌", style="Success.TButton",
                   command=self.apply_license_plate).pack(side="left")

    # ---- 地图 / 公司 ----
    def _build_map_tab(self, parent):
        ttk.Label(parent, text="地图与公司", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="一键解锁全图公司、车库、城市等。",
                  style="Status.TLabel").pack(anchor="w", pady=(4, 12))

        self.map_info_var = StringVar(value="未加载")
        ttk.Label(parent, textvariable=self.map_info_var,
                  style="Status.TLabel").pack(anchor="w", pady=(0, 12))

        actions = [
            ("🌍 解锁全部公司 (discovered=true)",
             "将所有 company 单元标记为已发现。",
             self.discover_all),
            ("🏠 解锁全部车库 (garage.status=bought)",
             "将所有 garage 单元设置为已购买状态。",
             self.unlock_garages),
            ("👥 提升司机招募上限到 100",
             "将 recruit/driver_limit 字段提升到 100。",
             self.increase_recruit_limit),
            ("⭐ AI 司机满技能 + ADR 全开",
             "把所有 driver_ai 的 5 项技能设为 6.0、ADR 设为 63(危险品全认证)。",
             self.max_driver_skills),
            ("🚛 修复所有挂车磨损",
             "把所有 trailer 单元的车厢/底盘/车轮磨损 + 永久磨损 + 货物损坏归零。",
             self.repair_all_trailers),
            ("⏰ 延长任务期限 +72 小时",
             "把所有 job_offer_data 的 expiration_time 延长 72 小时(跳过 nil 占位)。",
             self.extend_jobs),
        ]
        for title, desc, cmd in actions:
            f = ttk.Frame(parent, style="Panel.TFrame")
            f.pack(fill="x", pady=4, padx=4)
            f_inner = ttk.Frame(f, style="Panel.TFrame")
            f_inner.pack(fill="x", padx=12, pady=8)
            ttk.Label(f_inner, text=title, style="Panel.TLabel",
                      font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
            ttk.Label(f_inner, text=desc, style="Status.TLabel").pack(anchor="w", pady=(2, 4))
            ttk.Button(f_inner, text="执行", style="Warn.TButton",
                       command=cmd).pack(anchor="e", pady=(4, 0))

    # ---- 通用行 ----
    def _build_input_row(self, parent, label, var, hint):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=4)
        ttk.Label(f, text=label, width=32, anchor="w").pack(side="left")
        entry = ttk.Entry(f, textvariable=var, width=24)
        entry.pack(side="left", padx=(8, 12))
        if hint:
            ttk.Label(f, text=hint, style="Status.TLabel").pack(side="left")

    # ============================================================
    # 状态 / 通知
    # ============================================================
    def _set_status(self, text: str, kind: str = "info"):
        self.status_var.set(text)
        # 简易颜色变化
        try:
            style = ttk.Style()
            color = {"info": "#9ca3af", "success": SUCCESS,
                     "warn": WARN, "err": ERR}.get(kind, "#9ca3af")
            style.configure("Status.TLabel", foreground=color)
        except Exception:
            pass

    def _toast(self, result: EditResult):
        if result.success:
            self._set_status(result.message, "success")
            messagebox.showinfo("操作成功", result.message)
        else:
            self._set_status(result.message, "err")
            messagebox.showerror("操作失败", result.message)

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
        try:
            self.sii = SiiFile.load(path)
            self.editor = SaveEditor(self.sii)
            self.current_path = path
            self.path_var.set(f"📂 {path}")
            self._populate_tabs()
            self.btn_save.config(state="normal")
            self.btn_saveas.config(state="normal")
            self._set_status(f"已加载存档: {os.path.basename(path)}", "success")
        except SiiParseError as e:
            messagebox.showerror("解析失败", str(e))
            self._set_status(f"解析失败: {e}", "err")
        except Exception as e:
            messagebox.showerror("加载失败", f"无法读取文件：\n{e}")
            self._set_status(f"加载失败: {e}", "err")

    def on_save(self):
        if not self.sii:
            return
        if not self.sii.is_dirty():
            self._set_status("存档未做任何修改。", "info")
            messagebox.showinfo("无需保存", "你没有修改任何内容。")
            return
        if self._auto_backup.get():
            try:
                bk = self.sii.backup(self.current_path)
                self._set_status(f"已自动备份到: {os.path.basename(bk)}", "info")
            except Exception as e:
                if not messagebox.askyesno("备份失败",
                        f"自动备份失败：{e}\n是否仍然继续保存?"):
                    return
        try:
            # 按原格式保存
            self.sii.save(self.current_path, binary=None)
            self._set_status(f"已保存: {os.path.basename(self.current_path)}", "success")
            messagebox.showinfo("保存成功",
                f"存档已写回:\n{self.current_path}\n\n"
                "建议先退出游戏再启动,以避免冲突。")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            self._set_status(f"保存失败: {e}", "err")

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

        # BSII 格式：只询问是否加密，不可转文本（否则游戏无法识别）
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
                # BSII 格式：保持结构,只控制是否加密
                self.sii.save(path, encrypted=bool(choice))
                self._set_status(f"已另存为: {os.path.basename(path)}", "success")
                messagebox.showinfo("保存成功", f"已另存为:\n{path}")
            except Exception as e:
                messagebox.showerror("保存失败", str(e))
                self._set_status(f"保存失败: {e}", "err")
            return

        # 非 BSII：让用户选择保存格式（含 ScsC 加密）
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
            # choice=True 加密保存；choice=False 文本保存
            self.sii.save(path, encrypted=bool(choice), binary=False)
            self._set_status(f"已另存为: {os.path.basename(path)}", "success")
            messagebox.showinfo("保存成功", f"已另存为:\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            self._set_status(f"保存失败: {e}", "err")

    def _fmt_label(self) -> str:
        if not self.sii:
            return "未加载"
        # BSII 二进制结构化格式（ETS2 1.5+/ATS 默认）
        if self.sii._bsii is not None:
            if self.sii._encrypted:
                return "BSII 二进制结构 + ScsC 加密 (ETS2 1.6 默认)"
            return "BSII 二进制结构 (明文)"
        if self.sii._encrypted:
            return "ScsC 加密 (AES-256-CBC + zlib)"
        if self.sii._binary:
            return "二进制 zlib (0x03 头)"
        return "明文文本"

    def _default_save_dir(self):
        """返回默认存档目录（Windows）。"""
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
            # 品牌型号显示(若都为空则显示车牌号)
            brand_model = f"{info['brand']} {info['model']}".strip()
            if not brand_model and info.get("license_plate"):
                brand_model = f"车牌: {info['license_plate']}"
            elif not brand_model:
                brand_model = "(无品牌型号信息)"
            self.truck_info_var.set(
                f"卡车实例: {info['instance']}   {brand_model}")
            # 燃油 — 若是 fuel_relative(0-1 比例),显示比例;否则显示绝对值
            if info["fuel_is_relative"]:
                self.fuel_var.set(f"{info['fuel']*100:.1f}%")  # 显示为百分比
            else:
                self.fuel_var.set(f"{info['fuel']:.1f}")
            self.fuel_cap_var.set(f"{info['fuel_capacity']:.1f}")
            self.odo_var.set(f"{info['odometer']:.1f}")
            for prop, _ in TRUCK_WEAR_PROPS:
                if prop in info:
                    self.wear_vars[prop].set(f"{info[prop]:.4f}")
                else:
                    self.wear_vars[prop].set("0.0000")
            # 车牌号(纯文本,已剥掉 UI 标记)
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

    # ---- 金钱 ----
    def _parse_int(self, s: str) -> int | None:
        s = s.strip().replace(",", "")
        try:
            return int(float(s))
        except ValueError:
            return None

    def _parse_float(self, s: str) -> float | None:
        s = s.strip().replace(",", "").rstrip("fF")
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
            messagebox.showerror("输入错误", "现金账户必须是数字")
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

        self._after_edit(f"已修改 {changed} 项金钱/贷款字段", msg)

    def _apply_money_preset(self, amount):
        if not self.editor:
            return
        self.money_var.set(str(amount))
        r = self.editor.set_money(amount)
        self._after_edit(r.message, [r.message])

    def pay_off_loan(self):
        if not self.editor:
            return
        r = self.editor.pay_off_loan()
        self.loan_var.set("0")
        self._after_edit(r.message, [r.message])

    # ---- XP / 等级 ----
    def apply_xp_level(self):
        if not self.editor:
            return
        msg = []
        lv = self._parse_int(self.level_var.get())
        if lv is not None:
            r = self.editor.set_level(lv)
            if r.success: msg.append(r.message)
        else:
            messagebox.showerror("输入错误", "等级必须是整数")
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

        self._after_edit("等级 / 经验 / 技能已应用", msg)

    def _apply_level_preset(self, level):
        if not self.editor:
            return
        self.level_var.set(str(level))
        # 粗略估算对应 XP
        xp = max(0, level * level * 1500)
        self.xp_var.set(str(xp))
        r1 = self.editor.set_level(level)
        r2 = self.editor.set_xp(xp)
        self._after_edit(f"已设置等级为 Lv.{level}（估算 XP={xp:,}）",
                         [r1.message, r2.message])

    def max_skills(self):
        if not self.editor:
            return
        r = self.editor.max_all_skills()
        for prop, _, _ in SKILLS:
            self.skill_vars[prop].set("6.0")
        self._after_edit(r.message, [r.message])

    # ---- 卡车 ----
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

        self._after_edit("卡车参数已应用", msg)

    def full_fuel(self):
        if not self.editor:
            return
        r = self.editor.full_fuel()
        # 更新显示
        info = self.editor.get_truck_info()
        if info["found"]:
            self.fuel_var.set(f"{info['fuel']:.1f}")
        self._after_edit(r.message, [r.message])

    def repair_truck(self):
        if not self.editor:
            return
        r = self.editor.repair_truck()
        for prop, _ in TRUCK_WEAR_PROPS:
            self.wear_vars[prop].set("0.0000")
        self._after_edit(r.message, [r.message])

    # ---- 地图 ----
    def discover_all(self):
        if not self.editor:
            return
        r = self.editor.discover_all_companies()
        self._after_edit(r.message, [r.message])
        # 更新地图信息
        companies = self.editor.list_companies()
        if companies:
            discovered = sum(1 for c in companies if
                self.sii.get_property(c.instance_name, "discovered", "false") == "true")
            self.map_info_var.set(
                f"共 {len(companies)} 家公司,其中 {discovered} 家已发现")

    def unlock_garages(self):
        if not self.editor:
            return
        r = self.editor.unlock_all_garages()
        self._after_edit(r.message, [r.message])

    def increase_recruit_limit(self):
        if not self.editor:
            return
        r = self.editor.set_recruit_limit(100)
        self._after_edit(r.message, [r.message])

    # ---- AI 司机 / 挂车 / 任务 ----
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
        self._after_edit(r.message, [r.message])

    def apply_license_plate(self):
        if not self.editor:
            return
        plate = self.plate_var.get().strip()
        if not plate:
            messagebox.showerror("输入错误", "车牌号不能为空")
            return
        r = self.editor.set_truck_license_plate(plate)
        self._after_edit(r.message, [r.message])

    # ---- 通用收尾 ----
    def _after_edit(self, summary: str, details: list):
        if details:
            self._set_status(summary, "success")
            messagebox.showinfo("操作完成", "\n".join(details))
        else:
            self._set_status(summary, "warn")
        self.refresh_overview()


def main():
    root = Tk()
    app = SaveEditorApp(root)
    # 如果传入了文件路径参数，自动加载
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(100, lambda: (app.on_open_arg(sys.argv[1])))
    root.mainloop()


# 用于支持命令行参数加载
def _patch_open_arg():
    """为 SaveEditorApp 增加 on_open_arg 方法的兼容补丁。"""
    def on_open_arg(self, path):
        # 复用 on_open 逻辑
        try:
            self.sii = SiiFile.load(path)
            self.editor = SaveEditor(self.sii)
            self.current_path = path
            self.path_var.set(f"📂 {path}")
            self._populate_tabs()
            self.btn_save.config(state="normal")
            self.btn_saveas.config(state="normal")
            self._set_status(f"已加载存档: {os.path.basename(path)}", "success")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
    SaveEditorApp.on_open_arg = on_open_arg


_patch_open_arg()


if __name__ == "__main__":
    main()
