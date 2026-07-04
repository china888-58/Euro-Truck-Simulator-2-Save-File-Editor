"""
ETS2 / ATS 存档文件 (.sii) 解析器
=====================================
支持两种格式：
  1. 文本格式（已被 SII Decrypt 解密，或游戏 mod 输出）
  2. 二进制 zlib 压缩格式（游戏原生存档）

设计目标：采用「行级补丁」策略，仅修改目标属性行，
       保留所有原始格式 / 注释 / 顺序，避免破坏存档结构。
"""

from __future__ import annotations

import os
import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# ETS2 / ATS 存档格式签名（前 4 字节）：
#   "SiiN" / "SiiNunit" = 明文文本（旧版/解密后）
#   0x03 + 头          = zlib 压缩（旧版二进制）
#   "ScsC"             = AES-256-CBC 加密 + zlib 压缩（ETS2 1.5+ / ATS 默认）
#   "BSII"             = 二进制结构化格式
#   "3nK\x01"          = 3nK 编码（本地化）
HEADER_TEXT_MAGIC = b"SiiNunit"
HEADER_BIN_FLAG = 0x03

# --- 加密格式（ScsC）常量 -----------------------------------------------
# 密钥来源：JohnnyGuitar 的 Savegame Decrypter 工具（社区公开）
# 参考: https://forum.scssoft.com/viewtopic.php?f=34&t=164103
SCSC_SIGNATURE = b"ScsC"          # 文件头 4 字节
SCSC_AES_KEY = bytes([
    0x2a, 0x5f, 0xcb, 0x17, 0x91, 0xd2, 0x2f, 0xb6,
    0x02, 0x45, 0xb3, 0xd8, 0x36, 0x9e, 0xd0, 0xb2,
    0xc2, 0x73, 0x71, 0x56, 0x3f, 0xbf, 0x1f, 0x3c,
    0x9e, 0xdf, 0x6b, 0x11, 0x82, 0x5a, 0x5d, 0x0a,
])
SCSC_HEADER_SIZE = 56   # 4(sig) + 32(hmac) + 16(iv) + 4(datasize)

# 单元声明： unit_type : unit_name {    或   unit_type : unit_name{
# unit_name 可能是普通名字（player、economy_unit）或 _nameless.XXXX.YYYY
UNIT_DECL_RE = re.compile(
    r"^([\t ]*)([A-Za-z_][\w.]*)\s*:\s*([^\s{]+)\s*\{\s*$"
)

# 属性行： property_name: value
# 名称允许包含数组下标，如 accessories[0]、wheels_wear[1]、user_mirror_rot[3]
PROP_RE = re.compile(
    r"^([\t ]*)([A-Za-z_][\w\[\]]*)\s*:\s*(.+?)\s*$"
)

# 嵌套类型属性行（如 truck : _nameless.xxx { ... }）已由 UNIT_DECL_RE 捕获


@dataclass
class Unit:
    """一个 SII 单元的描述信息。"""
    type_name: str               # 单元类型，如 player、economy_unit
    instance_name: str           # 实例名，如 player、_nameless.4F2C.8620
    indent: str                 # 行首缩进
    body_start_line: int         # 属性行起始（开括号下一行，0-based）
    body_end_line: int           # 闭括号所在行（含），0-based
    properties: Dict[str, Tuple[int, str, str]] = field(default_factory=dict)
    # properties: name -> (line_idx, indent, raw_value)


class SiiParseError(Exception):
    """SII 解析错误。"""


class SiiFile:
    """解析后的 SII 文件结构。

    使用方式：
        sf = SiiFile.load("game.sii")
        sf.set_property("player", "player_level", 10)
        sf.save("game.sii")
    """

    def __init__(self, lines: List[str], binary: bool, raw_bytes: bytes,
                 encrypted: bool = False, bsii=None):
        self._lines: List[str] = lines              # 当前文本行（含 \n）
        self._binary: bool = binary                 # 是否为 zlib 压缩格式
        self._encrypted: bool = encrypted           # 是否为 ScsC 加密格式
        self._bsii = bsii                            # BsiiFile 实例（BSII 格式时非 None）
        self._raw_bytes: bytes = raw_bytes          # 二进制原文（用于结构保存）
        self.units: Dict[str, Unit] = {}            # instance_name -> Unit
        self._dirty = False
        if bsii is not None:
            # BSII 格式：填充 units 字典，让外部代码无感知
            self._populate_units_from_bsii()
        else:
            self._parse()

    def _populate_units_from_bsii(self):
        """从 BsiiFile 填充 units 字典，让 SaveEditor 等代码无感知"""
        from bsii_parser import BsiiDataBlock
        for db in self._bsii.data_blocks:
            # 把 BsiiDataBlock 包装成 Unit-like
            u = Unit(
                type_name=db.type_name,
                instance_name=db.instance_name,
                indent="",
                body_start_line=0,
                body_end_line=0,
            )
            # properties: Dict[str, Tuple[int, indent, value_text]]
            # 这里我们用一个特殊标记 -1 表示这是 BSII 字段（行号无意义）
            for fname, ftext in db.field_raw.items():
                u.properties[fname] = (-1, "", ftext)
            self.units[db.instance_name] = u

    # ---------------- 公共 API ----------------
    @classmethod
    def load(cls, path: str) -> "SiiFile":
        """加载并解析 .sii 文件。"""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"存档文件不存在: {path}")

        with open(path, "rb") as f:
            raw = f.read()

        # 0.5) BSII 二进制结构化格式（ETS2 1.5+/ATS 默认）
        if raw.startswith(b"BSII"):
            try:
                from bsii_parser import BsiiFile
                bf = BsiiFile.from_bytes(raw)
                # 返回一个空文本但带 bsii 的 SiiFile
                return cls(lines=["SiiNunit {\n}\n"], binary=False,
                           raw_bytes=raw, encrypted=False, bsii=bf)
            except Exception as e:
                raise SiiParseError(f"BSII 解析失败：{e}")

        # 0.6) ScsC 加密格式 — 解密后可能是 SiiNunit 文本，也可能是 BSII 二进制
        if raw.startswith(SCSC_SIGNATURE):
            try:
                plaintext = SiiFile._decrypt_scsc_to_bytes(raw)
            except SiiParseError:
                raise
            except Exception as e:
                raise SiiParseError(
                    f"ScsC 加密存档解密失败：{e}\n"
                    "请确认已安装 pycryptodome：pip install pycryptodome"
                )
            # 根据解密后内容分发
            if plaintext.startswith(b"BSII"):
                try:
                    from bsii_parser import BsiiFile
                    bf = BsiiFile.from_bytes(plaintext)
                    return cls(lines=["SiiNunit {\n}\n"], binary=False,
                               raw_bytes=raw, encrypted=True, bsii=bf)
                except Exception as e:
                    raise SiiParseError(f"加密 BSII 解析失败：{e}")
            elif plaintext.startswith(b"SiiNunit") or plaintext.startswith(b"SiiN"):
                text = plaintext.decode("utf-8", errors="replace")
                lines = text.splitlines(keepends=True)
                if not lines:
                    raise SiiParseError("解密后存档为空。")
                return cls(lines, binary=False, raw_bytes=raw, encrypted=True)
            else:
                raise SiiParseError(
                    "ScsC 解密成功，但内容既不是 SiiNunit 文本也不是 BSII 二进制。\n"
                    f"前 16 字节: {plaintext[:16].hex(' ')}"
                )

        binary, encrypted, text = cls._decode_bytes(raw)
        lines = text.splitlines(keepends=True)
        if not lines:
            raise SiiParseError("存档文件为空。")
        return cls(lines, binary=binary, raw_bytes=raw, encrypted=encrypted)

    def get_text(self) -> str:
        """返回当前（可能已被修改的）文本内容。"""
        if self._bsii is not None:
            return self._bsii.to_text()
        return "".join(self._lines)

    @staticmethod
    def _decode_bytes(raw: bytes) -> Tuple[bool, bool, str]:
        """识别并解码 .sii 字节流。

        Returns:
            (binary_flag, encrypted_flag, decoded_text)
        """
        # 0) ScsC 加密格式（ETS2 1.5+ / ATS 新版本默认）
        if raw.startswith(SCSC_SIGNATURE):
            try:
                # _decrypt_scsc 会自动检测解密后是 BSII 还是 SiiNunit 文本
                text = SiiFile._decrypt_scsc(raw)
                return False, True, text
            except SiiParseError:
                raise
            except Exception as e:
                raise SiiParseError(
                    f"ScsC 加密存档解密失败：{e}\n"
                    "请确认已安装 pycryptodome：pip install pycryptodome"
                )

        # 1) 明文文本
        if raw.startswith(HEADER_TEXT_MAGIC):
            try:
                return False, False, raw.decode("utf-8")
            except UnicodeDecodeError:
                # 少见：可能含 latin-1 字符
                return False, False, raw.decode("latin-1")

        # 2) zlib 压缩
        # ETS2 二进制头： 0x03 0x04 ... 后面是 zlib 流（通常从偏移 4 或 8 开始）
        if raw and raw[0] == HEADER_BIN_FLAG:
            # 尝试常见偏移：4、8、0
            for offset in (4, 8, 2, 0):
                try:
                    data = zlib.decompress(raw[offset:])
                    text = data.decode("utf-8", errors="replace")
                    if "SiiNunit" in text:
                        return True, False, text
                except zlib.error:
                    continue
            # 整段尝试
            try:
                data = zlib.decompress(raw)
                return True, False, data.decode("utf-8", errors="replace")
            except zlib.error:
                pass

        # 3) 直接是 zlib 流（无头）
        try:
            data = zlib.decompress(raw)
            text = data.decode("utf-8", errors="replace")
            if "SiiNunit" in text:
                return True, False, text
        except zlib.error:
            pass

        # 4) fallback：按 utf-8 当文本
        try:
            text = raw.decode("utf-8")
            if "SiiNunit" in text:
                return False, False, text
        except UnicodeDecodeError:
            pass

        raise SiiParseError(
            "无法识别的 .sii 文件格式。\n"
            "支持的格式：\n"
            "  - 明文文本 (SiiNunit)\n"
            "  - zlib 压缩 (0x03 头)\n"
            "  - AES-256-CBC 加密 (ScsC 头，ETS2 1.5+/ATS 新版默认)\n"
            "如确认为加密存档但解密失败，请运行：pip install pycryptodome"
        )

    @staticmethod
    def _decrypt_scsc_to_bytes(raw: bytes) -> bytes:
        """解密 ScsC 加密的 SII 存档,返回解密后的原始字节(不解压为文本)。

        用于判断解密后内容是 SiiNunit 文本还是 BSII 二进制。
        """
        if len(raw) < SCSC_HEADER_SIZE:
            raise SiiParseError("ScsC 存档文件过小，文件可能已损坏。")
        iv = raw[36:52]
        ciphertext = raw[SCSC_HEADER_SIZE:]
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
        except ImportError as e:
            raise SiiParseError(
                "解密 ScsC 加密存档需要 pycryptodome 库。\n"
                "请运行：pip install pycryptodome"
            ) from e
        cipher = AES.new(SCSC_AES_KEY, AES.MODE_CBC, iv)
        try:
            plaintext_padded = cipher.decrypt(ciphertext)
            plaintext = unpad(plaintext_padded, AES.block_size, style="pkcs7")
        except (ValueError, KeyError) as e:
            raise SiiParseError(f"AES 解密失败（密钥或文件损坏）：{e}")
        # 解密后通常是 zlib 压缩的
        try:
            decompressed = zlib.decompress(plaintext)
            return decompressed
        except zlib.error:
            # 未压缩,直接返回
            return plaintext

    @staticmethod
    def _decrypt_scsc(raw: bytes) -> str:
        """解密 ScsC 加密的 SII 存档。

        文件结构（共 56 字节头）:
          [0:4]    Signature  = "ScsC"
          [4:36]   HMAC-SHA256 (32 bytes，本解密器不校验)
          [36:52]  InitVector  (16 bytes，AES-CBC IV)
          [52:56]  DataSize    (UInt32 LE，密文长度)
          [56:]    AES-256-CBC 密文（解密后是 zlib 压缩数据）
        """
        if len(raw) < SCSC_HEADER_SIZE:
            raise SiiParseError("ScsC 存档文件过小，文件可能已损坏。")

        iv = raw[36:52]
        # data_size = int.from_bytes(raw[52:56], "little")  # 不强校验
        ciphertext = raw[SCSC_HEADER_SIZE:]

        # 延迟导入，避免未安装 pycryptodome 时整个模块无法 import
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
        except ImportError as e:
            raise SiiParseError(
                "解密 ScsC 加密存档需要 pycryptodome 库。\n"
                "请运行：pip install pycryptodome"
            ) from e

        cipher = AES.new(SCSC_AES_KEY, AES.MODE_CBC, iv)
        try:
            plaintext_padded = cipher.decrypt(ciphertext)
            plaintext = unpad(plaintext_padded, AES.block_size, style="pkcs7")
        except (ValueError, KeyError) as e:
            raise SiiParseError(f"AES 解密失败（密钥或文件损坏）：{e}")

        # 解密后可能是:
        #   a) zlib 压缩的 SiiNunit 文本（旧版加密存档）
        #   b) zlib 压缩的 BSII 二进制结构（ETS2 1.6 / ATS 新版默认）
        #   c) 未压缩的明文文本（极少见）
        decompressed: Optional[bytes] = None
        try:
            decompressed = zlib.decompress(plaintext)
        except zlib.error:
            # 也许根本没压缩，直接是文本/二进制
            decompressed = plaintext

        # 检测解压后内容的格式
        head = decompressed[:8]

        # a) 明文文本存档
        if head.startswith(b"SiiNunit") or head.startswith(b"SiiN"):
            try:
                return decompressed.decode("utf-8")
            except UnicodeDecodeError:
                return decompressed.decode("latin-1")

        # b) BSII 二进制结构化格式 — 当前不支持
        if head.startswith(b"BSII"):
            raise SiiParseError(
                "解密成功，但存档使用 BSII 二进制结构化格式（ETS2 1.6 默认）。\n"
                "本编辑器目前仅支持 SiiNunit 文本格式存档。\n\n"
                "解决方法（任选其一）：\n"
                "  方案 A：在游戏配置中改存档格式为文本\n"
                "    1. 用记事本打开:\n"
                "       C:\\Users\\<你>\\Documents\\Euro Truck Simulator 2\\steam_profiles\\<配置>\\config.cfg\n"
                "    2. 找到 uset g_save_format 这一行,把值改为 2:\n"
                "       uset g_save_format \"2\"\n"
                "    3. 进游戏,重新加载并保存该存档\n"
                "    4. 再用本编辑器打开 .sii,即可正常识别\n\n"
                "  方案 B:使用外部 SII_Decrypt 工具转换为文本\n"
                "    https://github.com/TheLazyTomcat/SII_Decrypt/releases\n"
                "    解密后用本编辑器打开文本文件\n\n"
                "  方案 C（不推荐）:重新加载存档前临时改格式,改完再设回"
            )

        # c) 未知格式 — 把前 32 字节信息抛出,便于诊断
        hex_head = decompressed[:32].hex(" ")
        try:
            text_head = decompressed[:64].decode("utf-8", errors="replace")
        except Exception:
            text_head = "<无法解码>"
        raise SiiParseError(
            "解密成功,但解压后内容格式未知,可能密钥不匹配或为未支持的格式。\n"
            f"前 32 字节 (hex): {hex_head}\n"
            f"前 64 字节 (text): {text_head!r}\n\n"
            "请把以上信息反馈给开发者,以便添加对该格式的支持。"
        )

    @staticmethod
    def _encrypt_scsc(text: str) -> bytes:
        """将文本加密为 ScsC 格式（用于保存回 ETS2 1.5+ 存档）。

        生成 16 字节随机 IV，AES-256-CBC + PKCS7，再 zlib 压缩。
        HMAC 字段填 0（游戏不强制校验）。
        """
        import os as _os
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
        except ImportError as e:
            raise SiiParseError(
                "加密保存需要 pycryptodome 库。\n"
                "请运行：pip install pycryptodome"
            ) from e

        # 1) zlib 压缩明文
        compressed = zlib.compress(text.encode("utf-8"))
        # 2) AES-256-CBC + PKCS7
        iv = _os.urandom(16)
        cipher = AES.new(SCSC_AES_KEY, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(compressed, AES.block_size, style="pkcs7"))
        # 3) 拼装 56 字节头
        header = bytearray()
        header += SCSC_SIGNATURE                 # 4  sig
        header += b"\x00" * 32                    # 32 HMAC（游戏不校验，留 0）
        header += iv                              # 16 IV
        header += len(ciphertext).to_bytes(4, "little")  # 4  DataSize
        return bytes(header) + ciphertext

    # ---------------- 解析 ----------------
    def _parse(self) -> None:
        """扫描行，建立单元索引。

        使用 brace 计数跟踪嵌套，识别顶级单元块。
        """
        brace_stack: List[Tuple[int, str, str, str]] = []
        # 元素：(line_idx, unit_type, instance_name, indent)
        # 栈记录每个未闭合单元的入口

        for i, line in enumerate(self._lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # 检测单元声明
            decl = UNIT_DECL_RE.match(line.rstrip("\r\n"))
            if decl:
                indent, type_name, inst_name = decl.group(1), decl.group(2), decl.group(3)
                brace_stack.append((i, type_name, inst_name, indent))
                continue

            # 检测闭括号
            if stripped == "}":
                if not brace_stack:
                    continue
                open_line, type_name, inst_name, indent = brace_stack.pop()
                # 仅记录有 instance_name 的顶级（栈空时）单元
                # 但也保留嵌套单元便于查找
                unit = Unit(
                    type_name=type_name,
                    instance_name=inst_name,
                    indent=indent,
                    body_start_line=open_line + 1,
                    body_end_line=i,
                )
                # 收集属性行
                self._collect_properties(unit)
                # 用 instance_name 作为 key；若已存在，保留后出现的（覆盖）
                self.units[inst_name] = unit

    def _collect_properties(self, unit: Unit) -> None:
        """扫描单元的属性行，记录每个属性的行号、缩进、原始值。"""
        for i in range(unit.body_start_line, unit.body_end_line):
            if i >= len(self._lines):
                break
            line = self._lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            m = PROP_RE.match(line.rstrip("\r\n"))
            if not m:
                continue
            indent, name, value = m.group(1), m.group(2), m.group(3)
            # 跳过嵌套单元声明（如 "truck: _nameless.X { ..."）
            if value.endswith("{") or value.startswith("&"):
                continue
            unit.properties[name] = (i, indent, value)

    # ---------------- 查询 ----------------
    def get_property(self, instance: str, prop: str, default: Optional[str] = None) -> Optional[str]:
        u = self.units.get(instance)
        if u is None or prop not in u.properties:
            return default
        return u.properties[prop][2]

    def get_unit(self, instance: str) -> Optional[Unit]:
        return self.units.get(instance)

    def find_units_by_type(self, type_name: str) -> List[Unit]:
        """根据单元类型查找所有单元。"""
        return [u for u in self.units.values() if u.type_name == type_name]

    def find_first_by_type(self, type_name: str) -> Optional[Unit]:
        for u in self.units.values():
            if u.type_name == type_name:
                return u
        return None

    def get_float(self, instance: str, prop: str, default: float = 0.0) -> float:
        v = self.get_property(instance, prop)
        if v is None:
            return default
        try:
            # 处理 OrdinalString(值用双引号包) / "1.0f" / "1.0" / "1" 等
            s = v.strip().strip('"').strip()
            return float(s.rstrip("fF").strip())
        except ValueError:
            return default

    def get_int(self, instance: str, prop: str, default: int = 0) -> int:
        v = self.get_property(instance, prop)
        if v is None:
            return default
        try:
            # 处理 OrdinalString(值用双引号包) / "1.0f" / "1" 等
            s = v.strip().strip('"').strip()
            return int(s.rstrip("fF").strip())
        except ValueError:
            try:
                return int(float(s.rstrip("fF").strip()))
            except ValueError:
                return default

    # ---------------- 修改 ----------------
    def set_property(self, instance: str, prop: str, value) -> bool:
        """修改指定单元的属性值。

        value 可以是 int / float / str。返回是否成功。
        """
        # BSII 格式：代理到 BsiiFile
        if self._bsii is not None:
            ok = self._bsii.set_property(instance, prop, value)
            if ok:
                # 同步更新 units 字典里的文本表示（让 get_property 立即看到新值）
                u = self.units.get(instance)
                if u is not None and prop in u.properties:
                    line_idx, indent, _ = u.properties[prop]
                    formatted = self._format_value(value, "")
                    u.properties[prop] = (line_idx, indent, formatted)
                self._dirty = True
            return ok

        u = self.units.get(instance)
        if u is None:
            return False
        if prop not in u.properties:
            return False
        line_idx, indent, old = u.properties[prop]
        # 保持原始值的格式风格：若是 "1.0f" 风格，浮点也加 f
        formatted = self._format_value(value, old)
        new_line = f"{indent}{prop}: {formatted}\n"
        # 保留行尾换行符差异（CRLF 兼容）
        old_line = self._lines[line_idx]
        if old_line.endswith("\r\n"):
            new_line = new_line.rstrip("\n") + "\r\n"
        self._lines[line_idx] = new_line
        u.properties[prop] = (line_idx, indent, formatted)
        self._dirty = True
        return True

    @staticmethod
    def _format_value(value, old_text: str) -> str:
        """根据旧值风格格式化新值，最大程度保持原格式。"""
        old = old_text.strip()
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            # 检查旧值是否带 'f' 后缀
            had_f = old.lower().endswith("f")
            # 用 6 位有效数字，去掉多余 0
            s = f"{value:.6f}".rstrip("0").rstrip(".")
            if had_f and not s.lower().endswith("f"):
                s += "f"
            return s if s else "0"
        return str(value)

    # ---------------- 保存 ----------------
    def is_dirty(self) -> bool:
        if self._bsii is not None:
            return self._dirty or self._bsii.is_dirty()
        return self._dirty

    def save(self, path: str, binary: Optional[bool] = None,
             encrypted: Optional[bool] = None) -> None:
        """将修改写回文件。

        参数优先级（前者覆盖后者）:
          encrypted=True  -> ScsC 加密格式（AES-256-CBC + zlib）
          binary=True     -> 旧版 zlib 二进制 (0x03 头)
          binary=False    -> 明文文本
          都为 None       -> 按原格式保存

        对于 BSII 格式：始终按原 BSII 结构回写（忽略 binary/encrypted 之外的格式选项），
        若原文件是 ScsC 加密的 BSII，则会重新加密。
        """
        use_encrypted = encrypted if encrypted is not None else self._encrypted
        use_binary = binary if binary is not None else self._binary
        if encrypted is False and binary is None:
            use_binary = False

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

        # BSII 格式：用 BsiiFile 序列化
        if self._bsii is not None:
            bsii_bytes = self._bsii.to_bytes()
            with open(path, "wb") as f:
                if use_encrypted:
                    # 加密的 BSII：把 BSII 字节 zlib 压缩后 AES 加密
                    # 注意：_encrypt_scsc 接受的是字符串,我们要传字节
                    # 所以需要一个字节版本
                    compressed = zlib.compress(bsii_bytes)
                    f.write(self._encrypt_scsc_bytes(compressed))
                else:
                    # 明文 BSII
                    f.write(bsii_bytes)
            self._dirty = False
            self._bsii._dirty = False
            return

        # 文本格式
        text = self.get_text()
        with open(path, "wb") as f:
            if use_encrypted:
                f.write(self._encrypt_scsc(text))
            elif use_binary:
                header = bytes([HEADER_BIN_FLAG, 0x04, 0x00, 0x00])
                compressed = zlib.compress(text.encode("utf-8"))
                f.write(header + compressed)
            else:
                f.write(text.encode("utf-8"))
        self._dirty = False

    @staticmethod
    def _encrypt_scsc_bytes(data: bytes) -> bytes:
        """加密原始字节数据为 ScsC 格式（用于 BSII 等二进制内容的加密保存）。

        与 _encrypt_scsc 不同：_encrypt_scsc 接受文本字符串并自动 zlib 压缩,
        本函数接受已压缩的字节流,直接 AES 加密。
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
        except ImportError as e:
            raise SiiParseError(
                "加密保存需要 pycryptodome 库。\n"
                "请运行：pip install pycryptodome"
            ) from e
        iv = os.urandom(16)
        cipher = AES.new(SCSC_AES_KEY, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(data, AES.block_size, style="pkcs7"))
        header = bytearray()
        header += SCSC_SIGNATURE
        header += b"\x00" * 32       # HMAC 留 0
        header += iv
        header += len(ciphertext).to_bytes(4, "little")
        return bytes(header) + ciphertext

    def backup(self, path: str) -> str:
        """创建备份文件，返回备份路径。"""
        base, ext = os.path.splitext(path)
        i = 0
        while True:
            bk = f"{base}.bak{i if i else ''}{ext}"
            if not os.path.exists(bk):
                shutil_copy(path, bk)
                return bk
            i += 1


def shutil_copy(src: str, dst: str) -> None:
    import shutil
    shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python sii_parser.py <file.sii>")
        sys.exit(1)
    sf = SiiFile.load(sys.argv[1])
    if sf._encrypted:
        fmt = "ScsC 加密 (AES-256-CBC + zlib)"
    elif sf._binary:
        fmt = "二进制 zlib (0x03 头)"
    else:
        fmt = "明文文本"
    print(f"格式: {fmt}")
    print(f"单元数: {len(sf.units)}")
    for name, u in sf.units.items():
        print(f"  [{u.type_name}] {name}  ({len(u.properties)} 属性)")
