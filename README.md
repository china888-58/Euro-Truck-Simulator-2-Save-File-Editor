# 欧卡 / 美卡 存档编辑器

基于 Python + Tkinter 的桌面 GUI 工具，用于编辑 **Euro Truck Simulator 2** 和 **American Truck Simulator** 的存档文件（`.sii`）。

支持 **明文文本** 和 **BSII 二进制结构**（ETS2 1.6+ / ATS 新版默认）两种存档格式，包含 ScsC 加密 / zlib 压缩 / 明文 BSII 等所有常见变体。

## 功能特性

### 💰 金钱 / 贷款
- 现金账户、银行存款、贷款余额、贷款上限修改
- 快捷预设（1 千万 / 1 亿 / 10 亿 / 999 亿）
- 一键还清贷款

### ⭐ 经验 / 技能
- 等级与经验值修改（含等级预设和 XP 估算）
- 5 项技能等级（长途运输 / 重载 / 易碎 / 紧急 / 机械驾驶）单独调整
- 一键全部技能满级

### 🚛 卡车 / 燃油
- 燃油、油箱容量、里程表修改（自动识别 `fuel_relative` 0-1 比例）
- 5 项磨损部件归零（普通修理）
- **永久磨损清零**（`*_wear_unfixable`，普通修理无法恢复）
- 车牌号修改（自动保留 `<offset>` / `<img>` UI 渲染标记和 `|country` 后缀）
- 自动从配件 `data_path` 解析品牌型号（如 Scania R）

### 🗺️ 地图 / 公司
- 解锁全部公司（`discovered = true`）
- 解锁全部未购买车库（不降级已升级的车库）
- 提升司机招募上限

### 👥 AI 司机 / 挂车 / 任务
- **AI 司机满技能 + ADR 全开** — 5 项技能设为 6.0、ADR 设为 63（危险品全认证）
- **修复所有挂车磨损** — 车厢 / 底盘 / 车轮磨损 + 永久磨损 + 货物损坏
- **延长任务期限** — 所有 `job_offer_data` 的 `expiration_time` 延长 72 小时

### 🛠️ 其他
- 保存前自动备份
- 另存为时可选加密 / 明文格式
- 格式感知：BSII 用 int 枚举，文本用字符串枚举，自动区分
- BSII 字段类型自动升级（如 `int32` → `int64`，避免溢出崩溃）

## 安装与运行

### 依赖
- Python 3.10+
- 仅依赖标准库（Tkinter、zlib 等），无需安装第三方包

### 运行

```bash
python main.py
```

或直接传入存档路径自动加载：

```bash
python main.py "C:\Users\<你>\Documents\Euro Truck Simulator 2\profiles\<id>\savegames\game.sii"
```

### 打包为 EXE

```bash
python build.py
```

## 支持的存档格式

| 格式 | 描述 | 支持 |
|---|---|---|
| 明文文本 | `SiiNunit { ... }` | ✓ 读写 |
| zlib 压缩 | `0x03` 头 + zlib 数据 | ✓ 读写 |
| ScsC 加密 | AES-256-CBC + zlib（ETS2 1.5+ 默认） | ✓ 读写 |
| BSII 二进制 | ETS2 1.6+ / ATS 新版默认 | ✓ 读写 |
| BSII + ScsC | BSII 二进制 + 加密 | ✓ 读写 |

## 项目结构

```
.
├── main.py            # GUI 主程序（Tkinter）
├── editor.py          # 高层编辑 API（SaveEditor 类）
├── sii_parser.py      # SII 文本/二进制解析器
├── bsii_parser.py     # BSII 二进制结构解析器
├── diagnose_sii.py    # 存档诊断工具
├── build.py           # EXE 打包脚本
├── build_exe.bat      # Windows 打包批处理
└── LICENSE
```

## BSII 格式限制

BSII 二进制格式有以下技术限制（由格式本身决定）：

- **数组字段不可修改** — `accessories[]`、`drivers[]`、`wheels_wear[]` 等 15 种 `T_ARR_*` 类型字段无法通过 API 修改
- **OrdinalString 只能改表内值** — 强行设置表外字符串会静默回退到默认值
- **Vec8 类型不可修改** — 位置/朝向字段（`truck_placement`）受此限制

## 使用建议

- **先退出游戏再编辑** — 避免文件冲突
- **保留自动备份** — 默认开启，编辑出错时可回滚
- **不要共享你的 `game.sii`** — 含个人进度和敏感数据，已在 `.gitignore` 中排除

## 许可证

见 [LICENSE](LICENSE)。

## 适用版本

- ETS2 1.5x / 1.6x
- ATS 新版

不同游戏版本 / Mod 可能使用不同字段名，编辑器已通过多别名候选清单做兼容（如 `wear_engine` ↔ `engine_wear`、`long_dist` ↔ `longdis` 等）。
