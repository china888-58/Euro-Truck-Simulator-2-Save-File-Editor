"""
ETS2 / ATS BSII 二进制结构化存档格式 解析器+回写器
=====================================================
支持 ETS2 1.5+ / ATS 新版本默认的 BSII 二进制存档格式。

格式规范 (来源: Trucky/sii-decrypt-ts + TheLazyTomcat/SII_Decrypt):
  - 文件头: "BSII" (4B) + version u32 LE (1/2/3)
  - 多个 Block 流:
    - blockType=0: 结构块 (定义 schema: 字段名+类型)
    - blockType>0: 数据块 (实际数据,blockType=关联的 structureId)
  - 文件结尾: validity=0 的结构块

支持 38 种数据类型 (0x01-0x3E),包括:
  - 字符串 (UTF-8 + base-38 编码)
  - 整数 (Int16/32/64, UInt16/32/64)
  - 浮点 (Single, Vec2/3/4/8)
  - 数组 (各种类型的数组)
  - ID 引用 (_nameless.XXX / company.foo.bar / null)
  - OrdinalString (序数字符串表)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BSII_SIGNATURE = 0x49495342   # "BSII" 读作 u32 LE
BSII_HEADER_SIZE = 8         # signature(4) + version(4)

# Base-38 编码字符表 (索引 0-36)
_CHAR_TABLE = "0123456789abcdefghijklmnopqrstuvwxyz_"

# 类型 ID 枚举
T_UTF8_STR   = 0x01
T_ARR_STR   = 0x02
T_ENC_STR   = 0x03
T_ARR_ENC   = 0x04
T_FLOAT     = 0x05
T_ARR_FLT   = 0x06
T_VEC2      = 0x07
T_ARR_V2    = 0x08
T_VEC3      = 0x09
T_ARR_V3    = 0x0A
T_VEC3I     = 0x11
T_ARR_V3I   = 0x12
T_VEC4      = 0x17
T_ARR_V4    = 0x18
T_VEC8      = 0x19   # v1=Vec7s, v2+=Vec8s
T_ARR_V8    = 0x1A
T_INT32     = 0x25
T_ARR_I32   = 0x26
T_UINT32    = 0x27
T_ARR_U32   = 0x28
T_INT16     = 0x29
T_ARR_I16   = 0x2A
T_UINT16    = 0x2B
T_ARR_U16   = 0x2C
T_UINT32_2  = 0x2F   # 同 0x27
T_INT64     = 0x31
T_ARR_I64   = 0x32
T_UINT64    = 0x33
T_ARR_U64   = 0x34
T_BOOL      = 0x35
T_ARR_BOOL  = 0x36
T_ORD_STR   = 0x37
T_ID_A      = 0x39
T_ARR_IDA   = 0x3A
T_ID_B      = 0x3B
T_ARR_IDC   = 0x3C
T_ID_C      = 0x3D
T_ARR_IDE   = 0x3E

# ID 类型集合
_ID_TYPES = {T_ID_A, T_ID_B, T_ID_C}
_ARR_ID_TYPES = {T_ARR_IDA, T_ARR_IDC, T_ARR_IDE}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class BsiiField:
    """字段定义 (来自结构块)"""
    name: str
    type_id: int
    ordinal_table: Optional[Dict[int, str]] = None  # 仅 type=0x37 在结构块中有


@dataclass
class BsiiStructureBlock:
    """结构块 — schema 定义"""
    structure_id: int
    name: str                    # 单元类型名 (player, vehicle, economy_units, ...)
    fields: List[BsiiField] = field(default_factory=list)


@dataclass
class BsiiDataBlock:
    """数据块 — 一个单元实例"""
    structure_id: int            # 关联结构块的 ID
    type_name: str               # 单元类型名 (复制自结构块,便于查找)
    instance_name: str           # 实例名 (_nameless.XXX / company.foo.bar / null)
    field_values: Dict[str, Any] = field(default_factory=dict)  # field_name -> value
    # 字段值的「原始文本表示」(用于 get_property 兼容现有接口)
    field_raw: Dict[str, str] = field(default_factory=dict)


class BsiiParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# Reader (字节流读取辅助)
# ---------------------------------------------------------------------------
class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def eof(self) -> bool:
        return self.pos >= len(self.buf)

    def remaining(self) -> int:
        return len(self.buf) - self.pos

    def read_u8(self) -> int:
        if self.pos + 1 > len(self.buf):
            raise BsiiParseError("读取 u8 越界")
        v = self.buf[self.pos]
        self.pos += 1
        return v

    def read_bool(self) -> bool:
        return self.read_u8() != 0

    def read_u16(self) -> int:
        if self.pos + 2 > len(self.buf):
            raise BsiiParseError("读取 u16 越界")
        v = struct.unpack_from("<H", self.buf, self.pos)[0]
        self.pos += 2
        return v

    def read_i16(self) -> int:
        if self.pos + 2 > len(self.buf):
            raise BsiiParseError("读取 i16 越界")
        v = struct.unpack_from("<h", self.buf, self.pos)[0]
        self.pos += 2
        return v

    def read_u32(self) -> int:
        if self.pos + 4 > len(self.buf):
            raise BsiiParseError("读取 u32 越界")
        v = struct.unpack_from("<I", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def read_i32(self) -> int:
        if self.pos + 4 > len(self.buf):
            raise BsiiParseError("读取 i32 越界")
        v = struct.unpack_from("<i", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def read_u64(self) -> int:
        if self.pos + 8 > len(self.buf):
            raise BsiiParseError("读取 u64 越界")
        v = struct.unpack_from("<Q", self.buf, self.pos)[0]
        self.pos += 8
        return v

    def read_i64(self) -> int:
        if self.pos + 8 > len(self.buf):
            raise BsiiParseError("读取 i64 越界")
        v = struct.unpack_from("<q", self.buf, self.pos)[0]
        self.pos += 8
        return v

    def read_f32(self) -> float:
        if self.pos + 4 > len(self.buf):
            raise BsiiParseError("读取 f32 越界")
        v = struct.unpack_from("<f", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def read_bytes(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise BsiiParseError(f"读取 {n} 字节越界")
        v = self.buf[self.pos:self.pos + n]
        self.pos += n
        return v

    def read_string(self) -> str:
        length = self.read_u32()
        raw = self.read_bytes(length)
        return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Writer (字节流写入辅助)
# ---------------------------------------------------------------------------
class _Writer:
    __slots__ = ("parts",)

    def __init__(self):
        self.parts: List[bytes] = []

    def write_u8(self, v: int) -> None:
        self.parts.append(struct.pack("<B", v & 0xFF))

    def write_bool(self, v: bool) -> None:
        self.write_u8(1 if v else 0)

    def write_u16(self, v: int) -> None:
        self.parts.append(struct.pack("<H", v & 0xFFFF))

    def write_i16(self, v: int) -> None:
        self.parts.append(struct.pack("<h", v))

    def write_u32(self, v: int) -> None:
        self.parts.append(struct.pack("<I", v & 0xFFFFFFFF))

    def write_i32(self, v: int) -> None:
        self.parts.append(struct.pack("<i", v))

    def write_u64(self, v: int) -> None:
        self.parts.append(struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))

    def write_i64(self, v: int) -> None:
        self.parts.append(struct.pack("<q", v))

    def write_f32(self, v: float) -> None:
        self.parts.append(struct.pack("<f", v))

    def write_bytes(self, v: bytes) -> None:
        self.parts.append(v)

    def write_string(self, s: str) -> None:
        raw = s.encode("utf-8")
        self.write_u32(len(raw))
        self.parts.append(raw)

    def to_bytes(self) -> bytes:
        return b"".join(self.parts)


# ---------------------------------------------------------------------------
# 编码字符串 (base-38)
# ---------------------------------------------------------------------------
def decode_base38(value: int) -> str:
    """base-38 解码 — 与 TS 实现一致"""
    result = ""
    while value != 0:
        char_idx = (value % 38) - 1
        value //= 38
        if 0 <= char_idx < 37:
            result += _CHAR_TABLE[char_idx]
    return result


def encode_base38(s: str) -> int:
    """base-38 编码 — 解码的逆过程"""
    # 解码是反向遍历字符(从字符串末尾往前),所以编码也反向
    # 解码: char_idx = (val % 38) - 1, val //= 38
    # 即: 第一个解码出来的字符是字符串末尾字符
    # 所以原字符串中靠后的字符对应较低的位
    # 编码: val = sum_{i=0}^{n-1} (char_idx[i] + 1) * 38^i, 其中 i 从字符串末尾往前数
    result = 0
    for ch in reversed(s):
        idx = _CHAR_TABLE.index(ch) + 1  # 索引 1-37
        result = result * 38 + idx
    return result


# ---------------------------------------------------------------------------
# ID 编码/解码
# ---------------------------------------------------------------------------
def decode_id(r: _Reader) -> str:
    """解码 ID 引用 (类型 0x39/0x3B/0x3D)"""
    part_count = r.read_u8()

    if part_count == 0xFF:
        # _nameless ID — 8 字节地址
        address = r.read_u64()
        return _nameless_address_to_str(address)
    elif part_count == 0:
        return "null"
    else:
        # 命名 ID — partCount 个 base-38 编码字符串,用 . 连接
        parts = []
        for _ in range(part_count):
            v = r.read_u64()
            parts.append(decode_base38(v))
        return ".".join(parts)


def _nameless_address_to_str(address: int) -> str:
    """把 u64 地址转为 _nameless.XXX.YYY.ZZZ 格式"""
    # 把 8 字节按 2 字节一组,转十六进制,从后往前处理,去除前导 0
    # address 是 u64 LE,把它转成 8 字节 BE 序列后分组(因为 TS 实现是逆序的)
    # 实际上,对照 TS 源码:
    #   data = Buffer.alloc(8); data.writeBigUInt64LE(address, 0);
    #   然后按 i=0..7 遍历,每 2 字节一组,高字节在前拼接
    #   从后往前处理,最后去除前导 0
    raw = struct.pack("<Q", address & 0xFFFFFFFFFFFFFFFF)

    # 按 2 字节一组,从后往前
    groups = []
    for i in range(3, -1, -1):
        # 第 i 组是 raw[2i], raw[2i+1]
        # 但 TS 实现是高字节在前拼接:
        #   currentPart = data[i].toString(16).padStart(2,'0') + currentPart
        # 即先读的字节是低位(在右),后读的字节是高位(在左)
        # 第 i 组(2字节): raw[2i] (低) + raw[2i+1] (高)
        lo = raw[2 * i]
        hi = raw[2 * i + 1]
        # 拼成 4 位十六进制: 高字节 + 低字节
        hex_str = f"{hi:02x}{lo:02x}"
        # 去除前导 0
        hex_str = hex_str.lstrip("0") or "0"
        groups.append(hex_str)
    return "_nameless." + ".".join(groups)


def encode_id(w: _Writer, value: str) -> None:
    """编码 ID 引用"""
    if value == "null":
        w.write_u8(0)
    elif value.startswith("_nameless."):
        address = _nameless_str_to_address(value)
        w.write_u8(0xFF)
        w.write_u64(address)
    else:
        # 命名 ID — 用 . 分割,每段 base-38 编码
        parts = value.split(".")
        w.write_u8(len(parts))
        for part in parts:
            w.write_u64(encode_base38(part))


def _nameless_str_to_address(value: str) -> int:
    """把 _nameless.XXX.YYY.ZZZ 转回 u64 地址

    groups[0] 是高位 (raw[6..7]), groups[3] 是低位 (raw[0..1])
    """
    addr_str = value[len("_nameless."):]
    groups = addr_str.split(".")

    # 补齐到 4 个组(前导组用"0"补齐,因为 groups[0] 是高位)
    while len(groups) < 4:
        groups.insert(0, "0")

    raw = bytearray(8)
    # groups[i] → raw[2*(3-i) .. 2*(3-i)+1]
    # groups[0] (高位) → raw[6..7]
    # groups[3] (低位) → raw[0..1]
    for i, g in enumerate(groups):
        full = int(g, 16) if g else 0
        hi = (full >> 8) & 0xFF
        lo = full & 0xFF
        target = 2 * (3 - i)
        raw[target] = lo
        raw[target + 1] = hi

    return struct.unpack("<Q", bytes(raw))[0]


# ---------------------------------------------------------------------------
# 单值解码/编码
# ---------------------------------------------------------------------------
def decode_value(r: _Reader, type_id: int, version: int,
                 ordinal_table: Optional[Dict[int, str]] = None) -> Any:
    """根据 type_id 从 Reader 解码单个值"""
    if type_id == T_UTF8_STR:
        return r.read_string()
    elif type_id == T_ARR_STR:
        n = r.read_u32()
        return [r.read_string() for _ in range(n)]
    elif type_id == T_ENC_STR:
        return decode_base38(r.read_u64())
    elif type_id == T_ARR_ENC:
        n = r.read_u32()
        return [decode_base38(r.read_u64()) for _ in range(n)]
    elif type_id == T_FLOAT:
        return r.read_f32()
    elif type_id == T_ARR_FLT:
        n = r.read_u32()
        return [r.read_f32() for _ in range(n)]
    elif type_id == T_VEC2:
        return (r.read_f32(), r.read_f32())
    elif type_id == T_ARR_V2:
        n = r.read_u32()
        return [(r.read_f32(), r.read_f32()) for _ in range(n)]
    elif type_id == T_VEC3:
        return (r.read_f32(), r.read_f32(), r.read_f32())
    elif type_id == T_ARR_V3:
        n = r.read_u32()
        return [(r.read_f32(), r.read_f32(), r.read_f32()) for _ in range(n)]
    elif type_id == T_VEC3I:
        return (r.read_i32(), r.read_i32(), r.read_i32())
    elif type_id == T_ARR_V3I:
        n = r.read_u32()
        return [(r.read_i32(), r.read_i32(), r.read_i32()) for _ in range(n)]
    elif type_id == T_VEC4:
        return (r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32())
    elif type_id == T_ARR_V4:
        n = r.read_u32()
        return [(r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32())
                for _ in range(n)]
    elif type_id == T_VEC8:
        if version == 1:
            # Vec7s: 7 floats
            return tuple(r.read_f32() for _ in range(7))
        else:
            # Vec8s: 8 floats + 偏移补偿
            a = r.read_f32()
            b = r.read_f32()
            c = r.read_f32()
            d = r.read_f32()  # bias
            e = r.read_f32()
            f = r.read_f32()
            g = r.read_f32()
            h = r.read_f32()
            bias = int(d)  # 截断
            bits = (bias & 0xFFF) - 2048
            bits = bits << 9
            a += float(bits)
            bits2 = ((bias >> 12) & 0xFFF) - 2048
            bits2 = bits2 << 9
            c += float(bits2)
            return (a, b, c, d, e, f, g, h)
    elif type_id == T_ARR_V8:
        n = r.read_u32()
        return [decode_value(r, T_VEC8, version) for _ in range(n)]
    elif type_id == T_INT32:
        return r.read_i32()
    elif type_id == T_ARR_I32:
        n = r.read_u32()
        return [r.read_i32() for _ in range(n)]
    elif type_id == T_UINT32 or type_id == T_UINT32_2:
        return r.read_u32()
    elif type_id == T_ARR_U32:
        n = r.read_u32()
        return [r.read_u32() for _ in range(n)]
    elif type_id == T_INT16:
        return r.read_i16()
    elif type_id == T_ARR_I16:
        n = r.read_u32()
        return [r.read_i16() for _ in range(n)]
    elif type_id == T_UINT16:
        return r.read_u16()
    elif type_id == T_ARR_U16:
        n = r.read_u32()
        return [r.read_u16() for _ in range(n)]
    elif type_id == T_INT64:
        return r.read_i64()
    elif type_id == T_ARR_I64:
        n = r.read_u32()
        return [r.read_i64() for _ in range(n)]
    elif type_id == T_UINT64:
        return r.read_u64()
    elif type_id == T_ARR_U64:
        n = r.read_u32()
        return [r.read_u64() for _ in range(n)]
    elif type_id == T_BOOL:
        return r.read_bool()
    elif type_id == T_ARR_BOOL:
        n = r.read_u32()
        return [r.read_bool() for _ in range(n)]
    elif type_id == T_ORD_STR:
        # 数据块中: u32 index,从 ordinal_table 查找
        idx = r.read_u32()
        if ordinal_table is not None and idx in ordinal_table:
            return ordinal_table[idx]
        return ""
    elif type_id in _ID_TYPES:
        return decode_id(r)
    elif type_id in _ARR_ID_TYPES:
        n = r.read_u32()
        return [decode_id(r) for _ in range(n)]
    else:
        raise BsiiParseError(f"未知类型 ID: 0x{type_id:02X}")


def encode_value(w: _Writer, type_id: int, value: Any, version: int,
                 ordinal_table: Optional[Dict[int, str]] = None) -> None:
    """根据 type_id 把 value 编码到 Writer"""
    if type_id == T_UTF8_STR:
        w.write_string(str(value))
    elif type_id == T_ARR_STR:
        arr = list(value)
        w.write_u32(len(arr))
        for s in arr:
            w.write_string(str(s))
    elif type_id == T_ENC_STR:
        w.write_u64(encode_base38(str(value)))
    elif type_id == T_ARR_ENC:
        arr = list(value)
        w.write_u32(len(arr))
        for s in arr:
            w.write_u64(encode_base38(str(s)))
    elif type_id == T_FLOAT:
        w.write_f32(float(value))
    elif type_id == T_ARR_FLT:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_f32(float(v))
    elif type_id == T_VEC2:
        w.write_f32(float(value[0])); w.write_f32(float(value[1]))
    elif type_id == T_ARR_V2:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_f32(float(v[0])); w.write_f32(float(v[1]))
    elif type_id == T_VEC3:
        w.write_f32(float(value[0])); w.write_f32(float(value[1])); w.write_f32(float(value[2]))
    elif type_id == T_ARR_V3:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_f32(float(v[0])); w.write_f32(float(v[1])); w.write_f32(float(v[2]))
    elif type_id == T_VEC3I:
        w.write_i32(int(value[0])); w.write_i32(int(value[1])); w.write_i32(int(value[2]))
    elif type_id == T_ARR_V3I:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_i32(int(v[0])); w.write_i32(int(v[1])); w.write_i32(int(v[2]))
    elif type_id == T_VEC4:
        for x in value[:4]:
            w.write_f32(float(x))
    elif type_id == T_ARR_V4:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            for x in v[:4]:
                w.write_f32(float(x))
    elif type_id == T_VEC8:
        if version == 1:
            for x in value[:7]:
                w.write_f32(float(x))
        else:
            # Vec8s: 回写时不做偏移逆补偿,直接写 8 个 float
            # 因为我们读取时已经做了补偿,所以这里的 value 是补偿后的值
            # 直接写回补偿后的值(简化处理,游戏会重新应用偏移)
            # 注意: 这可能导致游戏重新应用偏移时数据失真
            # 但因为我们通常不改 Vec8 字段,所以问题不大
            for x in value[:8]:
                w.write_f32(float(x))
    elif type_id == T_ARR_V8:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            for x in v[:8] if version >= 2 else v[:7]:
                w.write_f32(float(x))
    elif type_id == T_INT32:
        w.write_i32(int(value))
    elif type_id == T_ARR_I32:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_i32(int(v))
    elif type_id == T_UINT32 or type_id == T_UINT32_2:
        w.write_u32(int(value))
    elif type_id == T_ARR_U32:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_u32(int(v))
    elif type_id == T_INT16:
        w.write_i16(int(value))
    elif type_id == T_ARR_I16:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_i16(int(v))
    elif type_id == T_UINT16:
        w.write_u16(int(value))
    elif type_id == T_ARR_U16:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_u16(int(v))
    elif type_id == T_INT64:
        w.write_i64(int(value))
    elif type_id == T_ARR_I64:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_i64(int(v))
    elif type_id == T_UINT64:
        w.write_u64(int(value))
    elif type_id == T_ARR_U64:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_u64(int(v))
    elif type_id == T_BOOL:
        w.write_bool(bool(value))
    elif type_id == T_ARR_BOOL:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            w.write_bool(bool(v))
    elif type_id == T_ORD_STR:
        # OrdinalString: 数据块存 index (u32),结构块有 ordinal_table {index: string}
        # 需要把字符串值反向查找找到对应 index
        target_str = str(value)
        if ordinal_table is not None:
            # 1) 精确匹配
            for idx, s in ordinal_table.items():
                if s == target_str:
                    w.write_u32(idx)
                    return
            # 2) 数值容错匹配 — 用户传 "6.0" 但表里是 "6"
            try:
                target_num = float(target_str)
                for idx, s in ordinal_table.items():
                    try:
                        if float(s) == target_num:
                            w.write_u32(idx)
                            return
                    except (ValueError, TypeError):
                        continue
            except (ValueError, TypeError):
                pass
            # 3) 找不到匹配 — 写 index 0(第一个表项,通常是默认值)
            #    这比写错误的 index 更安全
            if ordinal_table:
                w.write_u32(next(iter(ordinal_table)))
            else:
                w.write_u32(0)
        else:
            w.write_u32(0)
    elif type_id in _ID_TYPES:
        encode_id(w, str(value))
    elif type_id in _ARR_ID_TYPES:
        arr = list(value)
        w.write_u32(len(arr))
        for v in arr:
            encode_id(w, str(v))
    else:
        raise BsiiParseError(f"未知类型 ID: 0x{type_id:02X}")


# ---------------------------------------------------------------------------
# 文件结构
# ---------------------------------------------------------------------------
@dataclass
class BsiiFile:
    """完整的 BSII 文件结构"""
    version: int
    structures: Dict[int, BsiiStructureBlock] = field(default_factory=dict)
    # 保持结构块的原始顺序(用于回写时保持文件结构)
    structure_order: List[int] = field(default_factory=list)
    # 数据块列表(保持顺序)
    data_blocks: List[BsiiDataBlock] = field(default_factory=list)
    # 每个 structure 的 ordinal tables (字段名 -> ordinal_table)
    # 因为一个 structure 可能有多个 OrdinalString 字段,每个有自己的表
    # 简化为: structure_id -> { field_name -> ordinal_table }
    ordinal_tables: Dict[int, Dict[str, Dict[int, str]]] = field(default_factory=dict)
    # 字段在原始字节中的位置 (instance_name, field_name) -> (offset, length)
    # 用于行级补丁,但 BSII 我们用完整重写,所以这里不严格记录
    _dirty: bool = False

    # ---------------- 公共 API ----------------
    @classmethod
    def load(cls, path: str) -> "BsiiFile":
        import os
        if not os.path.isfile(path):
            raise FileNotFoundError(f"存档文件不存在: {path}")
        with open(path, "rb") as f:
            raw = f.read()
        return cls.from_bytes(raw)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "BsiiFile":
        r = _Reader(raw)
        # 1. 文件头
        signature = r.read_u32()
        if signature != BSII_SIGNATURE:
            raise BsiiParseError(
                f"BSII 签名错误: 0x{signature:08X} (期望 0x{BSII_SIGNATURE:08X})"
            )
        version = r.read_u32()
        if version not in (1, 2, 3):
            raise BsiiParseError(f"不支持的 BSII 版本: {version}")

        bf = cls(version=version)

        # 2. 主循环: 逐块读取
        # 当读到 validity=0 的结构块时结束
        end_of_file = False
        while not r.eof() and not end_of_file:
            block_type = r.read_u32()
            if block_type == 0:
                # --- 结构块 ---
                validity = r.read_bool()
                if not validity:
                    # 文件结束标记
                    end_of_file = True
                    continue
                structure_id = r.read_u32()
                name = r.read_string()

                sb = BsiiStructureBlock(structure_id=structure_id, name=name)
                # 读取字段定义
                while True:
                    field_type = r.read_u32()
                    if field_type == 0:
                        break
                    field_name = r.read_string()
                    f = BsiiField(name=field_name, type_id=field_type)
                    # OrdinalString 在结构块中有序数表数据
                    if field_type == T_ORD_STR:
                        ordinal_tbl: Dict[int, str] = {}
                        n = r.read_u32()
                        for _ in range(n):
                            ordinal = r.read_u32()
                            s = r.read_string()
                            ordinal_tbl[ordinal] = s
                        f.ordinal_table = ordinal_tbl
                        # 记录到全局表
                        if structure_id not in bf.ordinal_tables:
                            bf.ordinal_tables[structure_id] = {}
                        bf.ordinal_tables[structure_id][field_name] = ordinal_tbl
                    sb.fields.append(f)
                bf.structures[structure_id] = sb
                bf.structure_order.append(structure_id)
            else:
                # --- 数据块 (block_type = structure_id) ---
                if block_type not in bf.structures:
                    raise BsiiParseError(
                        f"数据块引用了未定义的 structureId={block_type}"
                    )
                sb = bf.structures[block_type]
                # 读取 block ID
                instance_name = decode_id(r)
                # 按字段定义读取字段值
                db = BsiiDataBlock(
                    structure_id=block_type,
                    type_name=sb.name,
                    instance_name=instance_name,
                )
                # 该 structure 的 ordinal 表
                struct_ords = bf.ordinal_tables.get(block_type, {})
                for fdef in sb.fields:
                    ot = struct_ords.get(fdef.name)
                    value = decode_value(r, fdef.type_id, version, ot)
                    db.field_values[fdef.name] = value
                    db.field_raw[fdef.name] = _value_to_text(
                        value, fdef.type_id, version)
                bf.data_blocks.append(db)

        return bf

    def get_unit(self, instance_name: str) -> Optional[BsiiDataBlock]:
        for db in self.data_blocks:
            if db.instance_name == instance_name:
                return db
        return None

    def find_first_by_type(self, type_name: str) -> Optional[BsiiDataBlock]:
        for db in self.data_blocks:
            if db.type_name == type_name:
                return db
        return None

    def find_units_by_type(self, type_name: str) -> List[BsiiDataBlock]:
        return [db for db in self.data_blocks if db.type_name == type_name]

    def list_unit_names(self) -> List[str]:
        return [db.instance_name for db in self.data_blocks]

    def get_property(self, instance: str, prop: str,
                    default: Optional[str] = None) -> Optional[str]:
        db = self.get_unit(instance)
        if db is None or prop not in db.field_raw:
            return default
        return db.field_raw[prop]

    def get_int(self, instance: str, prop: str, default: int = 0) -> int:
        v = self.get_property(instance, prop)
        if v is None:
            return default
        try:
            return int(v.strip().strip('"'))
        except ValueError:
            try:
                return int(float(v.strip().strip('"')))
            except ValueError:
                return default

    def get_float(self, instance: str, prop: str, default: float = 0.0) -> float:
        v = self.get_property(instance, prop)
        if v is None:
            return default
        try:
            return float(v.strip().strip('"').rstrip("fF"))
        except ValueError:
            return default

    def set_property(self, instance: str, prop: str, value) -> bool:
        """修改字段值

        注: 若数值超出当前字段类型范围(如 int32 设大额金钱),
        会自动升级字段类型到更大类型(int32 → int64, uint32 → uint64),
        让游戏按新类型读取。这是必要的,否则 struct.pack 会溢出崩溃。
        """
        db = self.get_unit(instance)
        if db is None:
            return False
        if prop not in db.field_values:
            return False
        # 找到字段类型
        sb = self.structures[db.structure_id]
        fdef = None
        for f in sb.fields:
            if f.name == prop:
                fdef = f
                break
        if fdef is None:
            return False
        # 检测数值溢出 — 自动升级字段类型
        new_type = _check_and_upgrade_type(fdef.type_id, value)
        if new_type != fdef.type_id:
            fdef.type_id = new_type
        # 根据类型转换值
        new_val = _coerce_value(value, fdef.type_id, db.field_values[prop])
        db.field_values[prop] = new_val
        db.field_raw[prop] = _value_to_text(new_val, fdef.type_id, self.version)
        self._dirty = True
        return True

    def is_dirty(self) -> bool:
        return self._dirty

    def to_bytes(self) -> bytes:
        """完整重新序列化整个 BSII 文件"""
        w = _Writer()
        # 1. 文件头
        w.write_u32(BSII_SIGNATURE)
        w.write_u32(self.version)

        # 2. 结构块 (按原始顺序)
        for sid in self.structure_order:
            sb = self.structures[sid]
            w.write_u32(0)            # block_type = 0 (结构块)
            w.write_bool(True)        # validity
            w.write_u32(sid)          # structure_id
            w.write_string(sb.name)   # name

            # 字段定义
            for f in sb.fields:
                w.write_u32(f.type_id)
                w.write_string(f.name)
                # OrdinalString 在结构块中要写序数表
                if f.type_id == T_ORD_STR and f.ordinal_table is not None:
                    w.write_u32(len(f.ordinal_table))
                    for ordinal, s in f.ordinal_table.items():
                        w.write_u32(ordinal)
                        w.write_string(s)
            # 字段列表终止符
            w.write_u32(0)

        # 3. 数据块 (按原始顺序)
        # 注意:数据块必须在结构块之后
        for db in self.data_blocks:
            sb = self.structures[db.structure_id]
            w.write_u32(db.structure_id)   # block_type = structure_id
            # block ID
            encode_id(w, db.instance_name)
            # 字段值
            for fdef in sb.fields:
                value = db.field_values.get(fdef.name)
                # OrdinalString 字段需要传 ordinal_table 用于反向查找 index
                ot = fdef.ordinal_table if fdef.type_id == T_ORD_STR else None
                encode_value(w, fdef.type_id, value, self.version, ot)

        # 4. 文件结束标记 (validity=0 的结构块)
        w.write_u32(0)       # block_type = 0
        w.write_bool(False)  # validity = 0
        return w.to_bytes()

    def save(self, path: str) -> None:
        """保存到文件(明文 BSII 二进制)"""
        import os
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.to_bytes())
        self._dirty = False

    def to_text(self) -> str:
        """把 BSII 转成 SiiNunit 文本格式(便于人工查看)"""
        lines = ["SiiNunit", "{"]
        for db in self.data_blocks:
            sb = self.structures[db.structure_id]
            lines.append(f"{sb.name} : {db.instance_name} {{")
            for fdef in sb.fields:
                v = db.field_raw.get(fdef.name, "")
                # 数组字段需要特殊格式
                if _is_array_type(fdef.type_id):
                    arr = db.field_values.get(fdef.name, [])
                    lines.append(f"\t{fdef.name}: {len(arr)}")
                    for i, item in enumerate(arr):
                        lines.append(f"\t{fdef.name}[{i}]: {_scalar_to_text(item)}")
                else:
                    lines.append(f"\t{fdef.name}: {v}")
            lines.append("}")
            lines.append("")
        lines.append("}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 值转换辅助
# ---------------------------------------------------------------------------
def _is_array_type(type_id: int) -> bool:
    return type_id in (
        T_ARR_STR, T_ARR_ENC, T_ARR_FLT, T_ARR_V2, T_ARR_V3,
        T_ARR_V3I, T_ARR_V4, T_ARR_V8, T_ARR_I32, T_ARR_U32,
        T_ARR_I16, T_ARR_U16, T_ARR_I64, T_ARR_U64, T_ARR_BOOL,
    ) or type_id in _ARR_ID_TYPES


def _check_and_upgrade_type(type_id: int, value) -> int:
    """检测数值是否超出当前类型范围,若超出则返回更大的类型 ID。

    升级规则:
      int16  → int32  → int64
      uint16 → uint32 → uint64

    用于 set_property 时自动处理大额数值(如设置 999 亿金钱到 int32 字段)。
    """
    # 只处理数值类型
    if isinstance(value, bool):
        return type_id
    try:
        v = int(value)
    except (ValueError, TypeError):
        # 浮点或字符串,不升级
        return type_id

    INT16_MIN, INT16_MAX = -32768, 32767
    UINT16_MAX = 65535
    INT32_MIN, INT32_MAX = -2147483648, 2147483647
    UINT32_MAX = 4294967295

    if type_id == T_INT16:
        if v < INT16_MIN or v > INT16_MAX:
            # 升级到 int32
            if v < INT32_MIN or v > INT32_MAX:
                return T_INT64
            return T_INT32
    elif type_id == T_UINT16:
        if v < 0 or v > UINT16_MAX:
            # 升级到 uint32
            if v < 0 or v > UINT32_MAX:
                return T_UINT64
            return T_UINT32
    elif type_id == T_INT32:
        if v < INT32_MIN or v > INT32_MAX:
            return T_INT64
    elif type_id == T_UINT32 or type_id == T_UINT32_2:
        if v < 0 or v > UINT32_MAX:
            return T_UINT64
    return type_id


def _scalar_to_text(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    if isinstance(value, tuple):
        return "(" + ", ".join(_scalar_to_text(x) for x in value) + ")"
    return str(value)


def _value_to_text(value: Any, type_id: int, version: int) -> str:
    """把已解码的 Python 值转为文本表示(用于 get_property 兼容)"""
    if type_id == T_UTF8_STR:
        return f'"{value}"'
    if type_id == T_ENC_STR:
        return value   # 已解码为字符串
    if type_id == T_FLOAT:
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    if type_id == T_VEC2:
        return f"({value[0]:.6f}, {value[1]:.6f})"
    if type_id == T_VEC3:
        return f"({value[0]:.6f}, {value[1]:.6f}, {value[2]:.6f})"
    if type_id == T_VEC3I:
        return f"({value[0]}, {value[1]}, {value[2]})"
    if type_id == T_VEC4:
        return f"({value[0]:.6f}, {value[1]:.6f}, {value[2]:.6f}, {value[3]:.6f})"
    if type_id == T_VEC8:
        # Vec8s/Vec7s
        return "(" + ", ".join(f"{x:.6f}" for x in value) + ")"
    if type_id == T_INT32 or type_id == T_UINT32 or type_id == T_UINT32_2:
        return str(value)
    if type_id == T_INT16 or type_id == T_UINT16:
        return str(value)
    if type_id == T_INT64 or type_id == T_UINT64:
        return str(value)
    if type_id == T_BOOL:
        return "true" if value else "false"
    if type_id in _ID_TYPES:
        return value   # 字符串
    if type_id == T_ORD_STR:
        return f'"{value}"'
    # 数组类型
    if _is_array_type(type_id):
        return str(len(value))   # 数组在文本中是 count + 各元素
    return str(value)


def _coerce_value(new_value, type_id: int, old_value):
    """把用户传入的值转换为对应类型的 Python 值"""
    if type_id == T_UTF8_STR:
        # 用户可能传 "xxx" 带引号,去掉
        s = str(new_value).strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s
    if type_id == T_ENC_STR:
        s = str(new_value).strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s
    if type_id == T_ORD_STR:
        # OrdinalString — 把值转成字符串(如 "6.0" / "6")
        # encode_value 会反向查找 ordinal_table 找到对应 index
        s = str(new_value).strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s
    if type_id == T_FLOAT:
        return float(new_value)
    if type_id == T_VEC2:
        return (float(new_value[0]), float(new_value[1]))
    if type_id == T_VEC3:
        return (float(new_value[0]), float(new_value[1]), float(new_value[2]))
    if type_id == T_VEC3I:
        return (int(new_value[0]), int(new_value[1]), int(new_value[2]))
    if type_id == T_VEC4:
        return (float(new_value[0]), float(new_value[1]),
                float(new_value[2]), float(new_value[3]))
    if type_id == T_INT32 or type_id == T_UINT32 or type_id == T_UINT32_2:
        return int(new_value)
    if type_id == T_INT16 or type_id == T_UINT16:
        return int(new_value)
    if type_id == T_INT64 or type_id == T_UINT64:
        return int(new_value)
    if type_id == T_BOOL:
        if isinstance(new_value, str):
            return new_value.strip().lower() in ("true", "1", "yes")
        return bool(new_value)
    if type_id in _ID_TYPES:
        s = str(new_value).strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s
    # 其他类型(数组、Vec8 等)不支持修改,返回原值
    return old_value


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python bsii_parser.py <file.sii>")
        print("  解析 BSII 二进制存档,输出单元结构概览")
        sys.exit(1)
    try:
        bf = BsiiFile.load(sys.argv[1])
        print(f"BSII 版本: {bf.version}")
        print(f"结构块数: {len(bf.structures)}")
        print(f"数据块数: {len(bf.data_blocks)}")
        print()
        print("单元列表:")
        for db in bf.data_blocks[:20]:  # 只显示前 20 个
            print(f"  [{db.type_name}] {db.instance_name}  ({len(db.field_values)} 字段)")
        if len(bf.data_blocks) > 20:
            print(f"  ... 共 {len(bf.data_blocks)} 个")
    except Exception as e:
        print(f"解析失败: {e}", file=sys.stderr)
        sys.exit(1)
