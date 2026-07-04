"""
ETS2 / ATS 存档编辑器 — 高层操作封装
=====================================
基于 sii_parser.SiiFile，提供针对游戏特定单元的高层编辑 API。

游戏存档中的关键单元（注:实例名因版本/Mod 而异,编辑器会自动定位）：
  economy_unit : economy_units { money_account, loan_amount, bank_money, ... }
  player       : player_local { player_level, player_xp, skill_*, assigned_truck }
  vehicle      : _nameless.*  { fuel, odometer, wear_*, brand_id, model_id, ... }
  company      : company.*.*  { discovered, city_name, ... }

注：不同游戏版本/Mod 可能添加或省略某些字段，编辑器会优雅地跳过不存在的字段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sii_parser import SiiFile, Unit


# ETS2 / ATS 可升级的 5 项技能（属性名）
SKILLS = [
    ("skill_long_distance",  "长途运输", "Long Distance"),
    ("skill_heavy_cargo",    "重载货物", "Heavy Cargo"),
    ("skill_fragile_cargo",   "易碎货物", "Fragile Cargo"),
    ("skill_urgent_cargo",    "紧急货物", "Urgent Cargo"),
    ("skill_mechanical",     "机械驾驶", "Mechanical"),
]

# 卡车磨损部件属性
TRUCK_WEAR_PROPS = [
    ("wear_engine",       "引擎"),
    ("wear_transmission", "变速箱"),
    ("wear_cabin",       "驾驶室"),
    ("wear_chassis",     "底盘"),
    ("wear_wheels",      "车轮"),
    ("wear_onboard",     "车载设备"),
]

# ---------------------------------------------------------------------------
# 字段名别名候选 — 不同游戏版本/Mod 可能使用不同字段名
# 按优先级排序,第一个匹配的就使用
# ---------------------------------------------------------------------------
_FIELD_ALIASES = {
    # 玩家
    "player_level":       ["player_level", "level", "player_experience_level"],
    "player_xp":           ["player_xp", "xp", "experience", "experience_points",
                            "player_experience"],
    "assigned_truck":     ["assigned_truck", "current_truck", "truck", "assigned_vehicle"],
    "recruit_limit":      ["recruit_limit", "recruits_limit", "driver_limit",
                            "drivers_limit", "ai_unit_limit", "ai_drivers_limit",
                            "max_drivers", "max_ai_drivers"],
    # 经济
    # 注: ETS2 1.6 BSII 用 "bank" 作为玩家总金钱,不是 money_account
    #     bank_money 不能复用 bank(会跟现金冲突),要单独的字段名
    "money_account":      ["money_account", "money", "bank"],
    "loan_amount":         ["loan_amount", "loan", "current_loan"],
    "bank_money":         ["bank_money", "savings_account", "savings",
                            "bank_balance", "deposit"],
    "player_money_limit": ["player_money_limit", "money_limit", "loan_limit",
                            "credit_limit"],
    # 卡车 — 燃油
    # ETS2 1.6 BSII 用 fuel_relative (0-1 比例)，不存储绝对油量
    "fuel":               ["fuel", "current_fuel", "fuel_relative"],
    "fuel_capacity":      ["fuel_capacity", "tank_capacity"],
    "odometer":           ["odometer", "total_km", "odometer_value",
                            "integrity_odometer"],
    # 卡车 — 磨损部件
    # ETS2 1.6 BSII 用 engine_wear / cabin_wear (后缀),旧版用 wear_engine (前缀)
    "wear_engine":       ["wear_engine", "engine_wear"],
    "wear_transmission": ["wear_transmission", "transmission_wear"],
    "wear_cabin":         ["wear_cabin", "cabin_wear"],
    "wear_chassis":       ["wear_chassis", "chassis_wear"],
    "wear_wheels":        ["wear_wheels", "wheels_wear"],
    "wear_onboard":      ["wear_onboard", "onboard_wear"],
}

# ---------------------------------------------------------------------------
# 技能字段名别名候选
# ETS2 1.6 BSII 用简写: longdis / heavy / fragile / urgent / mechanical
# 旧版用前缀 skill_: skill_long_distance / skill_heavy_cargo / ...
# 按优先级排序,第一个匹配的就使用
# ---------------------------------------------------------------------------
_SKILL_ALIASES = {
    "skill_long_distance": ["skill_long_distance", "longdis", "long_distance",
                            "long_dist"],
    "skill_heavy_cargo":   ["skill_heavy_cargo",   "heavy",     "heavy_cargo"],
    "skill_fragile_cargo": ["skill_fragile_cargo", "fragile",   "fragile_cargo"],
    "skill_urgent_cargo":  ["skill_urgent_cargo",  "urgent",    "urgent_cargo"],
    "skill_mechanical":    ["skill_mechanical",    "mechanical"],
}

# 技能字段查找关键字 — 用于扫描单元查找含技能字段的单元
_SKILL_KEYWORDS = ("skill_", "longdis", "long_distance", "long_dist",
                   "heavy", "fragile", "urgent", "mechanical")

# ---------------------------------------------------------------------------
# ETS2 等级计算公式（社区已知）
#   level = floor(sqrt(xp / 5000)) + 1
#   xp_for_level(N) = 5000 * (N-1)^2
# 注: BSII 1.6 可能不存储 player_level,需要从 experience_points 反算
# ---------------------------------------------------------------------------
import math as _math
_XP_PER_LEVEL_BASE = 5000

def _level_from_xp(xp: int) -> int:
    """从经验值计算等级"""
    if xp <= 0:
        return 1
    return int(_math.sqrt(xp / _XP_PER_LEVEL_BASE)) + 1

def _xp_for_level(level: int) -> int:
    """计算达到指定等级所需的最小 XP"""
    level = max(1, int(level))
    return _XP_PER_LEVEL_BASE * (level - 1) * (level - 1)

# ---------------------------------------------------------------------------
# 单元类型名候选 — 不同游戏版本可能使用不同结构名
# ---------------------------------------------------------------------------
_PLAYER_TYPE_NAMES  = ("player", "player_local", "user_player", "player_data")
_ECONOMY_TYPE_NAMES = ("economy", "economy_units", "economy_unit")
_VEHICLE_TYPE_NAMES = ("vehicle", "vehicle_tractor", "truck", "player_truck",
                       "player_vehicle", "vehicle_automated", "tractor")
_GARAGE_TYPE_NAMES  = ("garage", "player_garage")
_COMPANY_TYPE_NAMES = ("company", "company_info")
_DRIVER_TYPE_NAMES  = ("driver_ai", "driver_gamepad", "driver")
_TRAILER_TYPE_NAMES = ("trailer", "player_trailer")
_JOB_OFFER_TYPE_NAMES = ("job_offer_data", "job_offer")


@dataclass
class EditResult:
    """单次编辑操作的结果。"""
    success: bool
    changed: int = 0            # 实际修改的字段数
    skipped: int = 0            # 字段不存在而跳过的数量
    message: str = ""

    @classmethod
    def ok(cls, changed: int = 1, skipped: int = 0, message: str = "") -> "EditResult":
        return cls(True, changed, skipped, message or f"已修改 {changed} 项")

    @classmethod
    def fail(cls, message: str) -> "EditResult":
        return cls(False, 0, 0, message)


class SaveEditor:
    """对 SiiFile 的高层操作集合。

    所有方法返回 EditResult，便于在 GUI 中提示用户。

    注：ETS2 / ATS 不同版本存档里单元实例名可能不同
    （economy_unit / economy_units / player / player_local / _nameless.X），
    因此 SaveEditor 在初始化时会自动扫描所有单元,定位真正含有目标属性的单元。
    """

    # 用于自动识别单元的「特征属性」（按字段名别名清单匹配）
    # 注意: player marker 只用 assigned_truck,不能用 player_xp 别名
    #       因为 ETS2 1.6 把 experience_points 放在 economy 单元里,
    #       若用 xp 作为 player marker 会把 economy 误识别为 player
    _ECONOMY_MARKER_PROPS = _FIELD_ALIASES["money_account"] + _FIELD_ALIASES["loan_amount"] \
                            + _FIELD_ALIASES["player_xp"]   # experience_points 也在 economy
    _PLAYER_MARKER_PROPS  = _FIELD_ALIASES["assigned_truck"]

    def __init__(self, sii: SiiFile):
        self.sii = sii
        # 自动定位 economy / player 单元的实例名
        self.economy_unit_name: str = self._locate_unit(
            self._ECONOMY_MARKER_PROPS, _ECONOMY_TYPE_NAMES, "economy")
        self.player_unit_name:  str = self._locate_unit(
            self._PLAYER_MARKER_PROPS,  _PLAYER_TYPE_NAMES,  "player")

    def _locate_unit(self, marker_props, fallback_types, default_name: str) -> str:
        """扫描所有单元,返回第一个含有任一 marker 属性的单元的 instance_name。

        优先级:
          1) 含有 marker 属性的单元（最可靠）
          2) 类型名匹配 fallback_types 中任一类型的第一个单元
          3) default_name（保留旧行为,让上层报"未找到字段"）
        """
        if isinstance(fallback_types, str):
            fallback_types = (fallback_types,)

        # 1) 按属性定位
        for name, u in self.sii.units.items():
            for p in marker_props:
                if p in u.properties:
                    return name
        # 2) 按类型名兜底
        for name, u in self.sii.units.items():
            if u.type_name in fallback_types:
                return name
        # 3) 返回默认名（向后兼容）
        return default_name

    # ============================================================
    # 通用 helper — 字段别名 / 规范化 ID / 错误信息
    # ============================================================
    def _set_field(self, instance: str, key: str, value) -> Tuple[bool, str]:
        """按 _FIELD_ALIASES[key] 候选清单设置字段。

        Returns: (success, matched_field_name)
        """
        if not instance:
            return False, ""
        u = self.sii.units.get(instance)
        if u is None:
            return False, ""
        aliases = _FIELD_ALIASES.get(key, [key])
        for p in aliases:
            if p in u.properties:
                if self.sii.set_property(instance, p, value):
                    return True, p
        return False, ""

    def _get_field_text(self, instance: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """按 _FIELD_ALIASES[key] 候选清单读取字段（文本值）。"""
        if not instance:
            return default
        u = self.sii.units.get(instance)
        if u is None:
            return default
        aliases = _FIELD_ALIASES.get(key, [key])
        for p in aliases:
            if p in u.properties:
                return self.sii.get_property(instance, p)
        return default

    def _get_field_int(self, instance: str, key: str, default: int = 0) -> int:
        v = self._get_field_text(instance, key)
        if v is None:
            return default
        try:
            return int(v.strip().strip('"').rstrip("fF"))
        except ValueError:
            try:
                return int(float(v.strip().strip('"').rstrip("fF")))
            except ValueError:
                return default

    def _get_field_float(self, instance: str, key: str, default: float = 0.0) -> float:
        v = self._get_field_text(instance, key)
        if v is None:
            return default
        try:
            return float(v.strip().strip('"').rstrip("fF"))
        except ValueError:
            return default

    def _available_fields(self, instance: str) -> List[str]:
        """返回该单元实际拥有的字段名清单（按字母序）"""
        u = self.sii.units.get(instance)
        if u is None:
            return []
        return sorted(u.properties.keys())

    def _fail_with_fields(self, msg: str, *instances: str) -> EditResult:
        """构造一个失败结果,并把相关单元的实际字段名附在末尾"""
        parts = [msg]
        for inst in instances:
            if inst and inst in self.sii.units:
                t = self.sii.units[inst].type_name
                fields = ", ".join(self._available_fields(inst)) or "<空>"
                parts.append(f"\n[{t} : {inst}] 字段列表: {fields}")
        return EditResult.fail("".join(parts))

    @staticmethod
    def _normalize_nameless_id(name: str) -> str:
        """规范化 _nameless.XXX.YYY.ZZZ — 去除每段前导 0

        例如 _nameless.0000.0001 与 _nameless.0.0.0.1 视为相同
        """
        if not name:
            return name
        if name.startswith("_nameless."):
            parts = name[len("_nameless."):].split(".")
            norm_parts = []
            for p in parts:
                # 去掉前导 0,但保留单个 "0"
                np = p.lstrip("0") or "0"
                norm_parts.append(np)
            return "_nameless." + ".".join(norm_parts)
        return name

    def _find_unit_by_id_normalized(self, ref: str) -> Optional[Unit]:
        """按规范化 _nameless ID 查找单元（容忍前导 0 差异）"""
        target = self._normalize_nameless_id(ref)
        for name, u in self.sii.units.items():
            if self._normalize_nameless_id(name) == target:
                return u
        return None

    # ============================================================
    # 玩家 — 金钱 / 贷款
    # ============================================================
    def get_money(self) -> int:
        return self._get_field_int(self.economy_unit_name, "money_account", 0)

    def set_money(self, amount: int) -> EditResult:
        ok, matched = self._set_field(self.economy_unit_name, "money_account", int(amount))
        if ok:
            return EditResult.ok(1, 0, f"现金设置为 €{amount:,}（字段: {matched}）")
        return self._fail_with_fields(
            f"未找到 money_account 字段（尝试单元: {self.economy_unit_name}）",
            self.economy_unit_name)

    def get_bank_money(self) -> int:
        return self._get_field_int(self.economy_unit_name, "bank_money", 0)

    def set_bank_money(self, amount: int) -> EditResult:
        ok, matched = self._set_field(self.economy_unit_name, "bank_money", int(amount))
        if ok:
            return EditResult.ok(1, 0, f"银行存款设置为 €{amount:,}（字段: {matched}）")
        # 失败 — ETS2 1.6 BSII 通常只有 bank 一个总金钱字段,没有独立银行存款
        return self._fail_with_fields(
            f"未找到 bank_money / savings 字段（尝试单元: {self.economy_unit_name}）\n\n"
            "■ 原因分析:\n"
            "  ETS2 1.6 BSII 通常只用一个 'bank' 字段存储玩家总金钱,\n"
            "  没有独立的「银行存款」概念。请用「现金账户」修改即可。\n\n"
            "■ 建议操作:\n"
            "  • 用「现金账户」(bank 字段) 直接修改玩家金钱",
            self.economy_unit_name)

    def get_loan(self) -> int:
        return self._get_field_int(self.economy_unit_name, "loan_amount", 0)

    def set_loan(self, amount: int) -> EditResult:
        ok, matched = self._set_field(self.economy_unit_name, "loan_amount", int(amount))
        if ok:
            return EditResult.ok(1, 0, f"贷款金额设置为 €{amount:,}（字段: {matched}）")
        return self._fail_with_fields(
            f"未找到 loan_amount 字段（尝试单元: {self.economy_unit_name}）",
            self.economy_unit_name)

    def pay_off_loan(self) -> EditResult:
        return self.set_loan(0)

    def set_loan_limit(self, limit: int) -> EditResult:
        ok, matched = self._set_field(self.economy_unit_name, "player_money_limit", int(limit))
        if ok:
            return EditResult.ok(1, 0, f"贷款上限设置为 €{limit:,}（字段: {matched}）")
        return self._fail_with_fields(
            f"未找到 player_money_limit 字段（尝试单元: {self.economy_unit_name}）",
            self.economy_unit_name)

    # ============================================================
    # 玩家 — XP / 等级 / 技能
    # ============================================================
    # 注: ETS2 1.6 BSII 把 experience_points 放在 economy 单元里,
    #     player_level 字段可能不存在(需从 xp 反算),
    #     所以 XP 查找要跨 player / economy 单元
    def _find_xp_holder(self) -> Tuple[str, str]:
        """返回 (unit_name, field_name) 找到 XP 所在位置。
        查找顺序: player 单元的 player_xp 别名 → economy 单元的 experience_points
        """
        # 1) player 单元
        if self.player_unit_name:
            u = self.sii.units.get(self.player_unit_name)
            if u is not None:
                for p in _FIELD_ALIASES["player_xp"]:
                    if p in u.properties:
                        return self.player_unit_name, p
        # 2) economy 单元
        if self.economy_unit_name:
            u = self.sii.units.get(self.economy_unit_name)
            if u is not None:
                for p in _FIELD_ALIASES["player_xp"]:
                    if p in u.properties:
                        return self.economy_unit_name, p
        return "", ""

    def get_xp(self) -> int:
        unit, prop = self._find_xp_holder()
        if not unit:
            return 0
        return self.sii.get_int(unit, prop, 0)

    def set_xp(self, amount: int) -> EditResult:
        amount = max(0, int(amount))
        unit, prop = self._find_xp_holder()
        if unit:
            if self.sii.set_property(unit, prop, amount):
                return EditResult.ok(1, 0,
                    f"经验值设置为 {amount:,} XP（{unit}.{prop}）")
        # 失败 — 给出友好错误
        return self._fail_with_fields(
            "未找到 player_xp / experience_points 字段 — 已在 player / economy 单元查找",
            self.player_unit_name, self.economy_unit_name)

    def get_level(self) -> int:
        """读取等级。
        查找顺序:
          1) player 单元的 player_level 别名(若直接存储)
          2) 否则从 experience_points 计算: level = floor(sqrt(xp/5000)) + 1
        """
        # 1) 直接读取
        if self.player_unit_name:
            u = self.sii.units.get(self.player_unit_name)
            if u is not None:
                for p in _FIELD_ALIASES["player_level"]:
                    if p in u.properties:
                        v = self.sii.get_int(self.player_unit_name, p, 0)
                        if v > 0:
                            return v
        # 2) 从 XP 反算
        xp = self.get_xp()
        return _level_from_xp(xp)

    def set_level(self, level: int) -> EditResult:
        """设置等级。
        策略:
          1) 若 player 单元有 player_level 字段,直接设置
          2) 否则通过设置 experience_points 间接达成目标等级
             (xp = 5000 * (level-1)^2,这是达到该等级所需最小 XP)
        """
        level = max(1, int(level))
        # 1) 直接设置
        if self.player_unit_name:
            u = self.sii.units.get(self.player_unit_name)
            if u is not None:
                for p in _FIELD_ALIASES["player_level"]:
                    if p in u.properties:
                        if self.sii.set_property(self.player_unit_name, p, level):
                            return EditResult.ok(1, 0,
                                f"等级设置为 {level}（{self.player_unit_name}.{p}）")
        # 2) 通过 XP 间接设置
        target_xp = _xp_for_level(level)
        r = self.set_xp(target_xp)
        if r.success:
            return EditResult.ok(1, 0,
                f"等级目标 {level} — 已设置经验值为 {target_xp:,} XP（等级从经验值自动计算）")
        # 3) 失败
        return self._fail_with_fields(
            f"无法设置等级 — 既找不到 player_level 字段,也无法设置 experience_points\n"
            f"目标等级 {level} 需要 {target_xp:,} XP",
            self.player_unit_name, self.economy_unit_name)

    def _find_skill_holder(self) -> str:
        """查找含有技能字段的单元(可能不在 player 单元里)

        使用 _SKILL_KEYWORDS 关键字清单匹配,支持 ETS2 1.6 BSII 的简写
        (longdis / heavy / fragile / urgent / mechanical) 和旧版 skill_ 前缀
        """
        def _has_skill_prop(u):
            for p in u.properties:
                pl = p.lower()
                for kw in _SKILL_KEYWORDS:
                    if kw in pl:
                        return True
            return False
        # 1) 优先 player 单元
        if self.player_unit_name:
            u = self.sii.units.get(self.player_unit_name)
            if u is not None and _has_skill_prop(u):
                return self.player_unit_name
        # 2) economy 单元(ETS2 1.6 把技能存在这里)
        if self.economy_unit_name:
            u = self.sii.units.get(self.economy_unit_name)
            if u is not None and _has_skill_prop(u):
                return self.economy_unit_name
        # 3) 扫描所有单元
        for name, u in self.sii.units.items():
            if _has_skill_prop(u):
                return name
        return ""

    def _find_skill_field(self, holder: str, prop: str) -> Optional[str]:
        """在指定单元里查找技能字段(按 _SKILL_ALIASES 候选清单)"""
        u = self.sii.units.get(holder)
        if u is None:
            return None
        aliases = _SKILL_ALIASES.get(prop, [prop])
        for p in aliases:
            if p in u.properties:
                return p
        return None

    def get_skill(self, prop: str) -> float:
        """读取技能值,按 _SKILL_ALIASES 候选清单查找字段"""
        # 优先 player 单元
        if self.player_unit_name:
            field = self._find_skill_field(self.player_unit_name, prop)
            if field:
                return self.sii.get_float(self.player_unit_name, field, 0.0)
        # 跨单元查找
        holder = self._find_skill_holder()
        if holder:
            field = self._find_skill_field(holder, prop)
            if field:
                return self.sii.get_float(holder, field, 0.0)
        return 0.0

    def set_skill(self, prop: str, level: float) -> EditResult:
        """设置技能值,按 _SKILL_ALIASES 候选清单查找字段"""
        level = max(0.0, min(6.0, float(level)))  # ETS2 技能上限 6 级
        # 1) 优先 player 单元
        if self.player_unit_name:
            field = self._find_skill_field(self.player_unit_name, prop)
            if field:
                if self.sii.set_property(self.player_unit_name, field, level):
                    return EditResult.ok(1, 0, f"{prop} = {level:.1f}（字段:{field}）")
        # 2) 跨单元查找
        holder = self._find_skill_holder()
        if holder:
            field = self._find_skill_field(holder, prop)
            if field:
                if self.sii.set_property(holder, field, level):
                    return EditResult.ok(1, 0,
                        f"{prop} = {level:.1f}（字段:{field},单元:{holder}）")
        # 3) 失败 — 给出友好提示
        return self._fail_with_fields(
            f"未找到 {prop} 字段 — 已扫描全部单元\n"
            f"尝试的字段名候选: {_SKILL_ALIASES.get(prop, [prop])}",
            self.player_unit_name, self.economy_unit_name)

    def max_all_skills(self) -> EditResult:
        """将全部 5 项技能提升到 6 级（满级）。

        支持 ETS2 1.6 BSII 简写(longdis/heavy/fragile/urgent/mechanical)
        和旧版 skill_xxx 命名两种格式。
        """
        # 找到技能所在单元
        holder = self._find_skill_holder()
        if not holder:
            return self._fail_with_fields(
                "未找到任何技能字段 — 已扫描全部单元\n"
                "已尝试关键字: " + ", ".join(_SKILL_KEYWORDS) + "\n\n"
                "■ 原因分析:\n"
                "  ETS2 1.6 BSII 存档可能不存储技能数据。\n"
                "  技能/等级/经验等数据可能存在以下位置:\n"
                "    1) 游戏内存(玩家在线时实时计算)\n"
                "    2) Steam 服务器端(云存档同步)\n"
                "    3) 独立的 stats.sii 文件\n"
                "    4) profile.sii 文件\n\n"
                "■ 建议操作:\n"
                "  • 在游戏内直接用控制台命令提升技能\n"
                "  • 检查 profile 目录下是否有独立 stats 文件\n"
                "  • 运行 diagnose_sii.py 查看其它 .sii 文件",
                self.player_unit_name, self.economy_unit_name)
        # 找到了技能单元 — 设置 5 项技能满级
        changed = 0
        skipped = 0
        matched_fields = []
        for prop, _, _ in SKILLS:
            field = self._find_skill_field(holder, prop)
            if field and self.sii.set_property(holder, field, 6.0):
                changed += 1
                matched_fields.append(field)
            else:
                skipped += 1
        if changed == 0:
            return self._fail_with_fields(
                f"已找到技能单元 {holder},但 5 项技能字段都不存在\n"
                "可能字段名已变更,请用 diagnose_sii.py 查看实际字段名",
                holder)
        return EditResult.ok(changed, skipped,
            f"已将 {changed} 项技能升至满级（单元: {holder}, 字段: {','.join(matched_fields)}）")

    def max_xp_for_top_level(self, target_level: int = 50) -> EditResult:
        """设置 XP 至「目标等级」所需值。

        使用 ETS2 官方公式: xp_for_level(N) = 5000 * (N-1)^2
        """
        xp = _xp_for_level(target_level)
        return self.set_xp(xp)

    # ============================================================
    # 卡车 — 燃油 / 里程 / 磨损
    # ============================================================
    def get_player_truck(self) -> Optional[Unit]:
        """返回玩家当前驾驶的卡车单元（player.assigned_truck 指向的 vehicle）。

        查找策略:
          1) 读 player.assigned_truck 引用,按规范化 _nameless ID 匹配单元
             (容忍前导 0 差异,如 _nameless.0000.0001 与 _nameless.0.0.0.1)
          2) 兜底: 在所有单元中按多种类型名查找
             (vehicle / vehicle_tractor / truck / player_truck / ...)
        """
        # 1) 通过 assigned_truck 引用查找
        truck_ref = self._get_field_text(self.player_unit_name, "assigned_truck")
        if truck_ref:
            ref = truck_ref.strip().strip('"')
            if ref and ref != "null":
                # 直接精确匹配
                truck = self.sii.get_unit(ref)
                if truck:
                    return truck
                # 规范化匹配（容忍前导 0 差异）
                truck = self._find_unit_by_id_normalized(ref)
                if truck:
                    return truck
        # 2) 兜底: 按多种类型名查找
        for ttype in _VEHICLE_TYPE_NAMES:
            u = self.sii.find_first_by_type(ttype)
            if u:
                return u
        return None

    def get_truck_prop(self, prop: str, default=0.0):
        """读取卡车字段（按字段别名查找）。"""
        truck = self.get_player_truck()
        if truck is None:
            return default
        aliases = _FIELD_ALIASES.get(prop, [prop])
        for p in aliases:
            if p in truck.properties:
                _, _, v = truck.properties[p]
                try:
                    return float(v.rstrip("fF").strip())
                except ValueError:
                    return v
        return default

    def set_truck_prop(self, prop: str, value) -> EditResult:
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车（vehicle）— 尝试以下方法:\n"
                "  1) 检查 player.assigned_truck 字段是否为有效引用\n"
                "  2) 该存档可能没有卡车单元（玩家未上车）",
                self.player_unit_name)
        aliases = _FIELD_ALIASES.get(prop, [prop])
        for p in aliases:
            if p in truck.properties:
                if self.sii.set_property(truck.instance_name, p, value):
                    return EditResult.ok(1, 0, f"卡车 {p} = {value}")
        return self._fail_with_fields(
            f"未找到卡车属性 {prop}（尝试候选:{aliases}）",
            truck.instance_name)

    def set_fuel(self, amount: float) -> EditResult:
        """设置燃油。

        ETS2 1.6 BSII 用 fuel_relative (0-1 比例),旧版用 fuel (绝对值)。
        策略:
          - 若字段是 fuel_relative: amount > 1 视为绝对值,除以 fuel_capacity(默认 600L)
          - 若字段是 fuel / current_fuel: 直接写绝对值
        """
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车 — 无法设置燃油",
                self.player_unit_name)
        aliases = _FIELD_ALIASES["fuel"]
        for p in aliases:
            if p in truck.properties:
                # fuel_relative 需要转换成 0-1 比例
                if p == "fuel_relative":
                    if 0.0 <= amount <= 1.0:
                        ratio = float(amount)
                    else:
                        # 视为绝对值,除以容量
                        cap = self.get_truck_prop("fuel_capacity", 0.0)
                        if cap <= 0:
                            cap = 600.0  # 默认容量
                        ratio = max(0.0, min(1.0, float(amount) / cap))
                    if self.sii.set_property(truck.instance_name, p, ratio):
                        return EditResult.ok(1, 0,
                            f"燃油比例设置为 {ratio*100:.0f}%（字段:{p}）")
                else:
                    # 绝对值字段
                    if self.sii.set_property(truck.instance_name, p, float(amount)):
                        return EditResult.ok(1, 0,
                            f"燃油设置为 {amount:.0f}L（字段:{p}）")
        return self._fail_with_fields(
            "无法设置 fuel 字段（尝试候选:" + ", ".join(aliases) + "）",
            truck.instance_name)

    def full_fuel(self) -> EditResult:
        """加满燃油。

        策略:
          - 若有 fuel_relative 字段: 设置为 1.0 (满)
          - 若有 fuel 字段且能读到 fuel_capacity: 设置为 fuel_capacity
          - 若有 fuel 字段但无 fuel_capacity: 设置为默认 600L
        """
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车 — 无法加满燃油",
                self.player_unit_name)
        aliases = _FIELD_ALIASES["fuel"]
        # 优先处理 fuel_relative
        if "fuel_relative" in truck.properties:
            if self.sii.set_property(truck.instance_name, "fuel_relative", 1.0):
                return EditResult.ok(1, 0, "燃油已加满（fuel_relative = 1.0）")
        # 否则用绝对值字段
        cap = self.get_truck_prop("fuel_capacity", 0.0)
        if cap <= 0:
            cap = 600.0  # 默认容量
        for p in aliases:
            if p == "fuel_relative":
                continue  # 已尝试过
            if p in truck.properties:
                if self.sii.set_property(truck.instance_name, p, float(cap)):
                    return EditResult.ok(1, 0, f"燃油已加满至 {cap:.0f}L（字段:{p}）")
        return self._fail_with_fields(
            "无法设置 fuel 字段（尝试候选:" + ", ".join(aliases) + "）",
            truck.instance_name)

    def set_odometer(self, km: float) -> EditResult:
        return self.set_truck_prop("odometer", float(km))

    def repair_truck(self) -> EditResult:
        """将卡车全部磨损部件归零（等效于全修）。

        支持 ETS2 1.6 BSII 的 xxx_wear 字段名(后缀)和旧版的 wear_xxx (前缀)。
        wheels_wear 是数组字段(每个轮子单独磨损),会清零所有 wheels_wear[i]。
        """
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车 — 无法修复",
                self.player_unit_name)
        changed = 0
        skipped = 0
        for prop, _ in TRUCK_WEAR_PROPS:
            # 用别名清单查找
            aliases = _FIELD_ALIASES.get(prop, [prop])
            ok = False
            for p in aliases:
                if p in truck.properties:
                    # wheels_wear 是数组字段,需整体替换所有元素
                    if prop == "wear_wheels":
                        arr = self.sii.get_array_elements(
                            truck.instance_name, p)
                        if arr:
                            n = len(arr)
                            if self.sii.set_array_elements(
                                truck.instance_name, p, [0.0] * n):
                                changed += 1
                                ok = True
                                break
                    if self.sii.set_property(truck.instance_name, p, 0.0):
                        changed += 1
                        ok = True
                        break
            if not ok:
                skipped += 1
        if changed == 0:
            return self._fail_with_fields(
                "未找到任何磨损字段 — 已尝试 wear_xxx 和 xxx_wear 两种命名",
                truck.instance_name)
        return EditResult.ok(changed, skipped, f"已修复 {changed} 个磨损部件（满血）")

    def get_truck_info(self) -> dict:
        """汇总当前卡车的关键信息用于展示。

        品牌型号从多候选字段读取:
          brand: brand_id / brand / make / manufacturer_id / manufacturer
          model: model_id / model / model_name / vehicle_model
        """
        truck = self.get_player_truck()
        info = {
            "found": truck is not None,
            "instance": truck.instance_name if truck else "",
            "brand": "",
            "model": "",
            "fuel": 0.0,
            "fuel_capacity": 0.0,
            "fuel_is_relative": False,   # 标记 fuel 字段是否为 0-1 比例
            "odometer": 0.0,
            "wear_engine": 0.0,
            "wear_transmission": 0.0,
            "wear_cabin": 0.0,
            "wear_chassis": 0.0,
            "wear_wheels": 0.0,
            "license_plate": "",         # 车牌号(若有)
        }
        if truck:
            # 品牌型号 — 多候选字段
            brand_aliases = ("brand_id", "brand", "make", "manufacturer_id",
                              "manufacturer", "brand_name")
            model_aliases = ("model_id", "model", "model_name", "vehicle_model",
                              "truck_model")
            for p in brand_aliases:
                if p in truck.properties:
                    v = truck.properties[p][2].strip().strip('"')
                    if v:
                        info["brand"] = v
                        break
            for p in model_aliases:
                if p in truck.properties:
                    v = truck.properties[p][2].strip().strip('"')
                    if v:
                        info["model"] = v
                        break
            # 兜底：从 accessories[*] 的 data_path 解析品牌型号
            # 例: /def/vehicle/truck/scania.s_2016/data.sii -> brand=Scania, model=S 2016
            if not info["brand"] or not info["model"]:
                bm = self._brand_model_from_accessories(truck)
                if bm:
                    if not info["brand"]:
                        info["brand"] = bm[0]
                    if not info["model"]:
                        info["model"] = bm[1]
            # 车牌号 — 剥掉 <offset>/<img> 等 UI 标记和 |country 后缀
            if "license_plate" in truck.properties:
                raw = truck.properties["license_plate"][2].strip('"')
                info["license_plate"] = self._clean_license_plate(raw)
            # 数值字段 — 用别名候选
            for key in ("fuel", "fuel_capacity", "odometer",
                        "wear_engine", "wear_transmission",
                        "wear_cabin", "wear_chassis", "wear_wheels"):
                aliases = _FIELD_ALIASES.get(key, [key])
                for p in aliases:
                    if p in truck.properties:
                        # 标记 fuel_relative
                        if key == "fuel" and p == "fuel_relative":
                            info["fuel_is_relative"] = True
                        # wheels_wear 是数组字段(每个轮子单独磨损值),
                        # 字段值是数组长度,真实磨损值在 wheels_wear[0..N]
                        if key == "wear_wheels":
                            arr = self.sii.get_array_elements(
                                truck.instance_name, p)
                            if arr:
                                vals = []
                                for raw in arr:
                                    try:
                                        vals.append(self._parse_hex_float(raw))
                                    except (ValueError, TypeError):
                                        pass
                                if vals:
                                    info[key] = max(vals)
                                    break
                        try:
                            # OrdinalString 字段值带双引号,先 strip
                            raw = truck.properties[p][2].strip().strip('"').strip()
                            info[key] = float(raw.rstrip("fF").strip())
                        except ValueError:
                            pass
                        break
        return info

    # ---- 卡车品牌型号 / 车牌清洗辅助 ----
    # data_path 形如 /def/vehicle/truck/<brand>.<model>/data.sii
    _TRUCK_DATA_PATH_RE = re.compile(
        r"/def/vehicle/truck/([^/]+)\.([^/]+)/data\.sii"
    )

    def _brand_model_from_accessories(self, truck: Unit) -> Optional[Tuple[str, str]]:
        """扫描卡车 accessories[*],从 data_path 解析 (brand, model)。

        优先匹配 .../truck/<brand>.<model>/data.sii 的主数据配件。
        返回格式化后的 (brand, model),如 ("Scania", "S 2016")。
        """
        # 收集 accessories[*] 引用的实例名
        # 文本格式: properties 里有 accessories[0]、accessories[1]...
        # BSII 格式: 数组整体存在 bsii.field_values["accessories"] 里(列表)
        refs: List[str] = []
        bsii = getattr(self.sii, "_bsii", None)
        if bsii is not None:
            db = bsii.get_unit(truck.instance_name)
            if db is not None:
                acc_list = db.field_values.get("accessories", [])
                if isinstance(acc_list, list):
                    for item in acc_list:
                        s = str(item).strip().strip('"')
                        if s and s != "null":
                            refs.append(s)
        else:
            ref_keys = [k for k in truck.properties if k.startswith("accessories[")]
            for k in ref_keys:
                ref = truck.properties[k][2].strip().strip('"')
                if ref and ref != "null":
                    refs.append(ref)

        for ref in refs:
            acc = self.sii.get_unit(ref)
            if acc is None:
                acc = self._find_unit_by_id_normalized(ref)
            if acc is None:
                continue
            dp = acc.properties.get("data_path", (None, None, ""))[2].strip().strip('"')
            if not dp:
                continue
            m = self._TRUCK_DATA_PATH_RE.search(dp)
            if m:
                brand_raw = m.group(1)
                model_raw = m.group(2)
                brand = " ".join(part.capitalize() for part in brand_raw.split("_"))
                model = " ".join(part.capitalize() for part in model_raw.split("_"))
                return (brand, model)
        return None

    @staticmethod
    def _clean_license_plate(raw: str) -> str:
        """清洗车牌字符串:去掉 <offset>/<img> 等 UI 渲染标记和 |country 后缀。

        例: "AT-449-AK.<offset hshift=5 vshift=-5><img src=/material/...>|france"
            -> "AT-449-AK."
        """
        # 去掉所有 <...> 标记
        cleaned = re.sub(r"<[^>]*>", "", raw)
        # 去掉 |country 后缀
        cleaned = cleaned.split("|", 1)[0]
        return cleaned.strip()

    @staticmethod
    def _parse_hex_float(raw):
        """解析 SII 文本格式里的 hex 浮点数(如 '&3a041ef4')。

        ETS2 文本存档里 float 字段以 '&'+8 位 hex 表示,大端 float32。
        BSII 格式下此函数不会被调用(数组元素已经是 float)。
        """
        import struct
        s = str(raw).strip()
        if s.startswith("&"):
            s = s[1:]
        # 取前 8 位 hex(若更长截断)
        s = s[:8].ljust(8, "0")
        return struct.unpack(">f", bytes.fromhex(s))[0]

    # ============================================================
    # 地图 / 城市 / 公司
    # ============================================================
    def list_companies(self) -> List[Unit]:
        """列出所有 company 单元（按多类型候选）。"""
        result: List[Unit] = []
        for ttype in _COMPANY_TYPE_NAMES:
            result.extend(self.sii.find_units_by_type(ttype))
        return result

    def discover_all_companies(self) -> EditResult:
        """将所有 company 单元设为已发现 (discovered: true)。"""
        companies = self.list_companies()
        if not companies:
            return EditResult.fail("未找到任何 company 单元（可能存档格式不同）")
        changed = 0
        skipped = 0
        for c in companies:
            if self.sii.set_property(c.instance_name, "discovered", True):
                changed += 1
            else:
                skipped += 1
        if changed == 0:
            return EditResult.fail("未找到任何 discovered 字段")
        return EditResult.ok(changed, skipped, f"已发现 {changed} 家公司")

    def unlock_all_garages(self) -> EditResult:
        """解锁所有未购买的车库（garage 单元的 status 字段）。

        ETS2 1.6 BSII 格式下 status 是整数枚举:
          0 = none (未购买)
          1 = bought (已购买,3 车位)
          2 = large (大型,5 车位)
          3 = large_full (大型满级)
        文本格式下 status 是字符串枚举名 ("none"/"bought"/"large"/"large_full")。

        本操作只把未购买(0/none)的车库设为 bought,不降级已升级的车库。
        """
        # 按多类型候选查找
        garages: List[Unit] = []
        for ttype in _GARAGE_TYPE_NAMES:
            garages.extend(self.sii.find_units_by_type(ttype))
        if not garages:
            return EditResult.fail("未找到任何 garage 单元")

        is_bsii = getattr(self.sii, "_bsii", None) is not None
        # BSII 用 int 1,文本用字符串 "bought"
        bought_val = 1 if is_bsii else "bought"
        none_markers = {"0", "none", ""}

        changed = 0
        skipped = 0
        already_owned = 0
        for g in garages:
            cur = self.sii.get_property(g.instance_name, "status")
            if cur is None:
                # 无 status 字段,尝试 discovered 兜底
                if self.sii.set_property(g.instance_name, "discovered", True):
                    changed += 1
                else:
                    skipped += 1
                continue
            cur_str = str(cur).strip().strip('"').lower()
            if cur_str in none_markers:
                if self.sii.set_property(g.instance_name, "status", bought_val):
                    changed += 1
                else:
                    skipped += 1
            else:
                # 已购买/已升级,跳过(不降级)
                already_owned += 1
        if changed == 0:
            if already_owned > 0:
                return EditResult.fail(
                    f"没有未购买的车库可解锁(已拥有 {already_owned} 个)")
            return EditResult.fail("无法设置任何 garage 字段")
        return EditResult.ok(
            changed, skipped,
            f"已解锁 {changed} 个车库(已拥有 {already_owned} 个保持不变)")

    def set_recruit_limit(self, limit: int) -> EditResult:
        """提高司机招募上限。

        查找策略:
          1) 在 player / economy 单元按 recruit_limit 别名候选清单查找
          2) 兜底: 扫描所有单元,找含有 recruit/driver_max 等关键字的数值型字段

        注: ETS2 1.6 BSII 用 drivers_offer (可招募司机数组) 和 driver_pool
            (已招募司机数组),没有"上限"字段 — 上限由车库数决定
        """
        aliases = _FIELD_ALIASES["recruit_limit"]
        # 1) 优先在 player / economy 单元查找
        for unit_name in (self.player_unit_name, self.economy_unit_name):
            ok, matched = self._set_field(unit_name, "recruit_limit", int(limit))
            if ok:
                return EditResult.ok(1, 0,
                    f"司机上限设置为 {limit}（{unit_name}.{matched}）")
        # 2) 兜底: 扫描所有单元,找含 recruit/driver_max 等关键字且数值型字段
        #    排除 driver_pool/drivers_offer (这些是数组,不是数值上限)
        keywords = ("recruit", "driver_limit", "driver_max", "max_driver",
                    "max_ai_driver", "drivers_limit")
        for name, u in self.sii.units.items():
            for p in list(u.properties.keys()):
                if p in ("driver_pool", "drivers_offer"):
                    continue  # 数组类型,跳过
                if any(kw in p.lower() for kw in keywords):
                    if self.sii.set_property(name, p, int(limit)):
                        return EditResult.ok(1, 0,
                            f"司机上限设置为 {limit}（{name}.{p}）")
        # 3) 失败 — 给出友好错误信息,解释 ETS2 1.6 真实情况
        # 找出真实存在的 driver 相关字段,供用户参考
        driver_fields = []
        for name, u in self.sii.units.items():
            for p in u.properties:
                if "driver" in p.lower() or "recruit" in p.lower():
                    driver_fields.append(f"{name}.{p}")
        msg = (
            "未找到司机上限字段 — 已尝试 player/economy 单元和全部单元扫描\n\n"
            "■ 原因分析:\n"
            "  ETS2 1.6 BSII 用以下字段管理司机:\n"
            "    • driver_pool   — 已招募司机数组\n"
            "    • drivers_offer — 当前可招募司机数组\n"
            "  没有专门的「招募上限」字段 — 上限由车库数决定(每个车库固定 5 人)\n\n"
            "■ 候选字段名清单(已尝试): " + ", ".join(aliases) + "\n"
        )
        if driver_fields:
            msg += "\n■ 实际存在的 driver/recruit 相关字段:\n"
            for f in driver_fields[:20]:
                msg += f"  • {f}\n"
        msg += (
            "\n■ 建议操作:\n"
            "  • 增加招募上限 = 多买车库(每车库 +5 司机位)\n"
            "  • 解锁全部车库功能已包含此效果,请用「解锁全部车库」按钮"
        )
        return self._fail_with_fields(msg,
            self.player_unit_name, self.economy_unit_name)

    # ============================================================
    # AI 司机 / 挂车 / 任务 — 批量操作
    # ============================================================
    def list_drivers(self) -> List[Unit]:
        """列出所有 AI 司机单元。"""
        result: List[Unit] = []
        for ttype in _DRIVER_TYPE_NAMES:
            result.extend(self.sii.find_units_by_type(ttype))
        return result

    def max_driver_skills(self) -> EditResult:
        """把所有 AI 司机的 5 项技能设为 6.0、ADR 设为 63。

        ETS2 1.6 BSII 用简写: long_dist/heavy/fragile/urgent/mechanical
        旧版用 skill_xxx 前缀,_SKILL_ALIASES 都已支持。
        ADR 是位掩码(0-63),63 = 全部 6 类危险品认证。
        """
        drivers = self.list_drivers()
        if not drivers:
            return EditResult.fail("未找到任何 driver_ai 单元")
        changed_drivers = 0
        changed_fields = 0
        for d in drivers:
            ok_any = False
            for prop in _SKILL_ALIASES:
                aliases = _SKILL_ALIASES[prop]
                for p in aliases:
                    if p in d.properties:
                        if self.sii.set_property(d.instance_name, p, 6.0):
                            changed_fields += 1
                            ok_any = True
                        break
            # ADR 全开(63 = 全部 6 位)
            for p in ("adr", "adr_cert", "hazardous"):
                if p in d.properties:
                    if self.sii.set_property(d.instance_name, p, 63):
                        changed_fields += 1
                        ok_any = True
                    break
            if ok_any:
                changed_drivers += 1
        if changed_drivers == 0:
            return EditResult.fail("未能修改任何司机的技能字段")
        return EditResult.ok(
            changed_drivers, 0,
            f"已为 {changed_drivers} 个 AI 司机满技能(6.0) + ADR 全开(63)"
            f"  共修改 {changed_fields} 个字段")

    def repair_truck_permanent(self) -> EditResult:
        """清零玩家卡车的「永久磨损」字段(*_wear_unfixable)。

        普通修理(repair_truck)只能清零可修复磨损;
        永久磨损只能通过此操作或换件清除。
        """
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车 — 无法清零永久磨损",
                self.player_unit_name)
        # 永久磨损字段名(后缀形式): xxx_wear_unfixable
        # 旧版可能用前缀: wear_xxx_unfixable
        # wheels_wear_unfixable 是数组字段(每轮单独),需整体替换
        targets = []
        for prop, cn in TRUCK_WEAR_PROPS:
            # 后缀形式 (ETS2 1.6 BSII)
            base = prop.replace("wear_", "")  # wear_engine -> engine
            targets.append(f"{base}_wear_unfixable")
            # 前缀形式 (旧版)
            targets.append(f"{prop}_unfixable")
        changed = 0
        skipped = 0
        for p in targets:
            if p in truck.properties:
                # 数组字段(如 wheels_wear_unfixable): 整体清零所有元素
                arr = self.sii.get_array_elements(truck.instance_name, p)
                if arr:
                    n = len(arr)
                    if self.sii.set_array_elements(
                        truck.instance_name, p, [0.0] * n):
                        changed += 1
                    continue
                if self.sii.set_property(truck.instance_name, p, 0.0):
                    changed += 1
            else:
                skipped += 1
        if changed == 0:
            return EditResult.ok(
                0, skipped,
                "卡车无永久磨损字段(可能本来就为 0 或存档版本不支持)")
        return EditResult.ok(
            changed, skipped,
            f"已清零 {changed} 项永久磨损(满血重生)")

    def list_trailers(self) -> List[Unit]:
        """列出所有挂车单元。"""
        result: List[Unit] = []
        for ttype in _TRAILER_TYPE_NAMES:
            result.extend(self.sii.find_units_by_type(ttype))
        return result

    def repair_trailers(self) -> EditResult:
        """修复所有挂车的磨损(车厢/底盘/车轮磨损 + 永久磨损 + 货物损坏)。"""
        trailers = self.list_trailers()
        if not trailers:
            return EditResult.fail("未找到任何 trailer 单元")
        wear_props = (
            "trailer_body_wear", "trailer_body_wear_unfixable",
            "chassis_wear", "chassis_wear_unfixable",
            "wheels_wear", "wheels_wear_unfixable",
            "cargo_damage",
        )
        changed_trailers = 0
        changed_fields = 0
        for t in trailers:
            ok_any = False
            for p in wear_props:
                if p in t.properties:
                    # wheels_wear / wheels_wear_unfixable 是数组字段
                    arr = self.sii.get_array_elements(t.instance_name, p)
                    if arr:
                        n = len(arr)
                        if self.sii.set_array_elements(
                            t.instance_name, p, [0.0] * n):
                            changed_fields += 1
                            ok_any = True
                        continue
                    if self.sii.set_property(t.instance_name, p, 0.0):
                        changed_fields += 1
                        ok_any = True
            if ok_any:
                changed_trailers += 1
        if changed_trailers == 0:
            return EditResult.fail("未能修改任何挂车的磨损字段")
        return EditResult.ok(
            changed_trailers, 0,
            f"已修复 {changed_trailers} 辆挂车(共 {changed_fields} 个字段)")

    def set_truck_license_plate(self, plate: str) -> EditResult:
        """设置玩家卡车的车牌号。

        plate 为纯文本车牌(如 'AB-123-CD'),不含 <offset>/<img> 标记。
        会保留原车牌的 UI 渲染标记和 |country 后缀(游戏内部需要)。
        """
        truck = self.get_player_truck()
        if truck is None:
            return self._fail_with_fields(
                "未找到玩家当前卡车 — 无法修改车牌",
                self.player_unit_name)
        if "license_plate" not in truck.properties:
            return EditResult.fail("卡车没有 license_plate 字段")
        raw = truck.properties["license_plate"][2].strip().strip('"')
        # 用新文本替换原车牌的纯文本部分,保留 <offset>/<img> 标记和 |country
        new_plate = self._replace_plate_text(raw, plate)
        if self.sii.set_property(truck.instance_name, "license_plate", new_plate):
            return EditResult.ok(1, 0, f"车牌已设置为: {plate}")
        return EditResult.fail("车牌写入失败")

    @staticmethod
    def _replace_plate_text(raw: str, new_text: str) -> str:
        """替换车牌字符串里的纯文本部分,保留 UI 标记和 |country 后缀。

        例: raw="AT-449-AK.<offset...><img...>|france", new="AB-123-CD"
            -> "AB-123-CD.<offset...><img...>|france"
        """
        # 找到第一个 < 或 | 的位置,前面就是纯文本部分
        idx = len(raw)
        for ch in ("<", "|"):
            i = raw.find(ch)
            if i >= 0 and i < idx:
                idx = i
        suffix = raw[idx:]
        return new_text + suffix

    def extend_job_offers(self, hours: int = 72) -> EditResult:
        """延长所有任务期限到当前最大值 + hours 小时。

        只处理 expiration_time 为数字的任务;nil 值(占位/过期任务)跳过。
        """
        jobs = []
        for ttype in _JOB_OFFER_TYPE_NAMES:
            jobs.extend(self.sii.find_units_by_type(ttype))
        if not jobs:
            return EditResult.fail("未找到任何 job_offer_data 单元")
        # 找出当前最大的过期时间作为基准(游戏内时间,分钟)
        max_exp = 0
        for j in jobs:
            raw = j.properties.get("expiration_time", (None, None, ""))[2].strip()
            if raw and raw != "nil":
                try:
                    v = int(raw)
                    if v > max_exp:
                        max_exp = v
                except ValueError:
                    pass
        if max_exp == 0:
            return EditResult.fail(
                "没有可延长的任务(全部 expiration_time 为 nil 或 0)")
        # 游戏内时间单位是分钟
        new_exp = max_exp + int(hours) * 60
        changed = 0
        skipped = 0
        for j in jobs:
            raw = j.properties.get("expiration_time", (None, None, ""))[2].strip()
            if not raw or raw == "nil":
                skipped += 1
                continue
            try:
                int(raw)  # 验证是数字
            except ValueError:
                skipped += 1
                continue
            if self.sii.set_property(j.instance_name, "expiration_time", new_exp):
                changed += 1
        if changed == 0:
            return EditResult.fail("未能延长任何任务期限")
        return EditResult.ok(
            changed, skipped,
            f"已延长 {changed} 个任务期限 +{hours} 小时"
            f"(基准 {max_exp} -> {new_exp},跳过 {skipped} 个 nil)")

    # ============================================================
    # 统计 / 摘要
    # ============================================================
    def summary(self) -> str:
        """生成存档摘要文本。"""
        lines = []
        lines.append(f"现金：€{self.get_money():,}")
        loan = self.get_loan()
        if loan:
            lines.append(f"贷款：€{loan:,}")
        try:
            bank = self.get_bank_money()
            if bank:
                lines.append(f"银行存款：€{bank:,}")
        except Exception:
            pass
        lines.append(f"等级：{self.get_level()}")
        lines.append(f"经验：{self.get_xp():,} XP")
        for prop, cn, _ in SKILLS:
            lines.append(f"  {cn}：{self.get_skill(prop):.1f}")
        info = self.get_truck_info()
        if info["found"]:
            brand = info["brand"] or "?"
            model = info["model"] or ""
            lines.append(f"卡车：{brand} {model}".strip())
            lines.append(f"  燃油：{info['fuel']:.0f} / {info['fuel_capacity']:.0f} L")
            lines.append(f"  里程：{info['odometer']:.0f} km")
            avg_wear = sum(info[k] for k in (
                "wear_engine", "wear_transmission",
                "wear_cabin", "wear_chassis", "wear_wheels")) / 5
            lines.append(f"  平均磨损：{avg_wear*100:.1f}%")
        companies = self.list_companies()
        if companies:
            discovered = sum(1 for c in companies if
                self.sii.get_property(c.instance_name, "discovered", "false") == "true")
            lines.append(f"公司：{discovered}/{len(companies)} 已发现")
        return "\n".join(lines)
