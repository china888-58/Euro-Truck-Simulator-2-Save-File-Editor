#!/usr/bin/env python3
"""
ETS2/ATS 存档格式诊断工具
=========================
用法:
    python diagnose_sii.py <your_save.sii>

输出文件头信息、加密状态、解密后内容的前 64 字节,以便判断存档格式。
"""
import sys
import os
import zlib


# ETS2 SII 已知的 AES 密钥 (来自社区公开的 Savegame Decrypter 工具)
SCSC_SIGNATURE = b"ScsC"
SCSC_AES_KEY = bytes([
    0x2a, 0x5f, 0xcb, 0x17, 0x91, 0xd2, 0x2f, 0xb6,
    0x02, 0x45, 0xb3, 0xd8, 0x36, 0x9e, 0xd0, 0xb2,
    0xc2, 0x73, 0x71, 0x56, 0x3f, 0xbf, 0x1f, 0x3c,
    0x9e, 0xdf, 0x6b, 0x11, 0x82, 0x5a, 0x5d, 0x0a,
])


def hexdump(data: bytes, length: int = 64) -> str:
    """以 hex+ascii 形式打印字节。"""
    out = []
    chunk = data[:length]
    for i in range(0, len(chunk), 16):
        row = chunk[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in row).ljust(48)
        ascii_part = "".join(
            chr(b) if 32 <= b < 127 else "." for b in row
        )
        out.append(f"  {i:04x}  {hex_part}  {ascii_part}")
    return "\n".join(out)


def diagnose(path: str) -> int:
    if not os.path.isfile(path):
        print(f"[错误] 文件不存在: {path}")
        return 1

    with open(path, "rb") as f:
        raw = f.read()

    print("=" * 64)
    print(f"文件: {path}")
    print(f"大小: {len(raw):,} 字节")
    print("=" * 64)
    print("原始文件头 (前 64 字节):")
    print(hexdump(raw, 64))
    print()

    sig = raw[:4]
    print(f"签名: {sig!r}  (hex: {sig.hex(' ')})")
    print()

    # 1) ScsC 加密格式
    if raw.startswith(SCSC_SIGNATURE):
        print("[格式] ScsC 加密 (AES-256-CBC + zlib)")
        if len(raw) < 56:
            print("[错误] 文件过小,可能已损坏。")
            return 1

        iv = raw[36:52]
        data_size = int.from_bytes(raw[52:56], "little")
        ciphertext = raw[56:]

        print(f"  IV (16 字节): {iv.hex(' ')}")
        print(f"  声明密文长度: {data_size:,} 字节")
        print(f"  实际密文长度: {len(ciphertext):,} 字节")
        print()

        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
        except ImportError:
            print("[错误] 需要安装 pycryptodome:")
            print("    pip install pycryptodome")
            return 1

        try:
            cipher = AES.new(SCSC_AES_KEY, AES.MODE_CBC, iv)
            plaintext_padded = cipher.decrypt(ciphertext)
            plaintext = unpad(plaintext_padded, AES.block_size, style="pkcs7")
        except Exception as e:
            print(f"[错误] AES 解密失败: {e}")
            print("可能原因:")
            print("  1. 文件损坏")
            print("  2. AES 密钥已变更 (新版游戏可能改了密钥)")
            return 1

        print("[OK] AES 解密成功")
        print(f"  解密后明文长度: {len(plaintext):,} 字节")
        print("  解密后前 64 字节:")
        print(hexdump(plaintext, 64))
        print()

        # 尝试 zlib 解压
        try:
            decompressed = zlib.decompress(plaintext)
            print(f"[OK] zlib 解压成功,解压后 {len(decompressed):,} 字节")
        except zlib.error as e:
            print(f"[警告] zlib 解压失败: {e}")
            print("  解密后内容可能未压缩,直接当文本/二进制处理。")
            decompressed = plaintext

        print()
        print("解压后内容前 128 字节:")
        print(hexdump(decompressed, 128))
        print()

        head8 = decompressed[:8]
        if head8.startswith(b"SiiNunit") or head8.startswith(b"SiiN"):
            print("[结论] 解压后是 SiiNunit 明文文本格式 ✅")
            print("  本编辑器应能正常处理该存档。")
            print("  如果你看到这条信息但仍报错,请把上面的 hex 内容反馈。")
        elif head8.startswith(b"BSII"):
            print("[结论] 解压后是 BSII 二进制结构化格式 ✅ (本编辑器已支持)")
            print()
            # 尝试解析并 dump 单元/字段名清单
            try:
                _dump_bsii_summary(decompressed)
            except Exception as e:
                print(f"[警告] BSII 解析失败: {e}")
        else:
            print(f"[结论] 解压后是未知格式:前 8 字节 = {head8!r}")
            print("  请把上面的 hex 内容反馈给开发者。")
        return 0

    # 2) 明文文本
    if raw.startswith(b"SiiNunit") or raw.startswith(b"SiiN"):
        print("[格式] 明文文本 (SiiNunit)")
        print("  本编辑器应能正常处理。")
        return 0

    # 3) 旧版 zlib 二进制 (0x03 头)
    if raw[0] == 0x03:
        print("[格式] 旧版 zlib 二进制 (0x03 头)")
        print("  本编辑器应能正常处理。")
        return 0

    # 4) 直接 BSII (无加密)
    if raw.startswith(b"BSII"):
        print("[格式] BSII 二进制结构化格式 (未加密) ✅ (本编辑器已支持)")
        print()
        try:
            _dump_bsii_summary(raw)
        except Exception as e:
            print(f"[警告] BSII 解析失败: {e}")
        return 0

    # 5) 未知
    print("[格式] 未知格式")
    print("  前 4 字节:", raw[:4].hex(' '), "=", raw[:4])
    return 1


def _dump_bsii_summary(raw: bytes) -> None:
    """解析 BSII 文件并 dump 所有单元/字段名清单"""
    # 复用项目主解析器
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bsii_parser import BsiiFile

    bf = BsiiFile.from_bytes(raw)
    print(f"BSII 版本: {bf.version}")
    print(f"结构块数: {len(bf.structures)}")
    print(f"数据块数: {len(bf.data_blocks)}")
    print()
    print("=" * 64)
    print("单元清单 (类型 + 实例名 + 字段名)")
    print("=" * 64)
    # 统计每个结构块出现的次数
    type_count = {}
    for db in bf.data_blocks:
        type_count[db.type_name] = type_count.get(db.type_name, 0) + 1
    print("类型统计:")
    for tname, n in sorted(type_count.items()):
        print(f"  {tname}: {n} 个")
    print()
    # 逐个列出前 N 个单元的字段名(全部)
    MAX_DUMP = 80
    for i, db in enumerate(bf.data_blocks):
        if i >= MAX_DUMP:
            print(f"  ... 共 {len(bf.data_blocks)} 个单元,只显示前 {MAX_DUMP} 个")
            break
        print(f"[{i+1}] {db.type_name} : {db.instance_name}")
        for fname, ftext in db.field_raw.items():
            # 字段名 = 文本值(截断到 60 字符)
            disp = ftext if len(ftext) <= 60 else (ftext[:57] + "...")
            print(f"      {fname} = {disp}")
    print()
    print("=" * 64)
    print("如果某个字段未找到,请检查上面的字段名清单")
    print("若实际字段名跟编辑器期望的不同,可能需要别名支持")
    print("=" * 64)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rc = diagnose(sys.argv[1])
    sys.exit(rc)


if __name__ == "__main__":
    main()
