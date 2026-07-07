<div align="center">

<img src="https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=A%20futuristic%20holographic%20truck%20icon%20in%20neon%20cyan%20and%20purple%20colors%2C%20minimal%20geometric%20design%2C%20dark%20background%2C%20sci-fi%20HUD%20style%2C%20glowing%20edges&image_size=square_hd" width="120" alt="Logo" />

# 欧卡 / 美卡 存档编辑器

**Euro Truck Simulator 2 · American Truck Simulator — Save File Editor**

[![Version](https://img.shields.io/badge/version-3.1.5-8b5cf6?style=for-the-badge)](https://github.com/china888-58/Euro-Truck-Simulator-2-Save-File-Editor/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-06b6d4?style=for-the-badge)](https://github.com/china888-58/Euro-Truck-Simulator-2-Save-File-Editor/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/china888-58/Euro-Truck-Simulator-2-Save-File-Editor/total?style=for-the-badge&color=f59e0b)](https://github.com/china888-58/Euro-Truck-Simulator-2-Save-File-Editor/releases)

</div>

---

## 🚀 快速开始

| 步骤 | 操作 |
|:---:|---|
| **1** | 从 [Releases](https://github.com/china888-58/Euro-Truck-Simulator-2-Save-File-Editor/releases/latest) 下载 `EuroTruckSaveEditor-Setup-v3.1.5.exe` |
| **2** | 双击安装，自动创建开始菜单和桌面快捷方式 |
| **3** | 启动程序 → 打开存档 → 修改数据 → 保存 → 进游戏 |

> **系统要求**：Windows 10 / 11（64 位）　·　首次运行被 SmartScreen 拦截请点击「更多信息」→「仍要运行」

---

## ✦ 功能矩阵

<table>
<tr>
<td width="50%">

### 💰 资产与金钱
- 现金账户 · 银行存款 · 贷款余额
- 快捷预设：`1000 万` / `1 亿` / `10 亿` / `999 亿`
- 一键还清全部贷款

### ⭐ 经验与技能
- 等级与经验值精确修改
- 6 项技能：长途 · 重载 · 易碎 · 紧急 · 机械 · ADR
- 一键全部技能满级

### 🚛 卡车与挂车
- 卡车部件磨损度修复（引擎/变速箱/底盘/轮胎/驾驶室）
- 一键加油 · 一键修复
- 挂车磨损度修复
- 定位当前驾驶车辆/挂车

</td>
<td width="50%">

### 🗺️ 地图与探索
- 一键解锁全部城市
- 一键解锁全部经销商
- 一键解锁全部车库
- 地图探索度一览

### 📦 货运市场
- 货运市场任务时间延长
- 货物市场任务管理
- 任务紧急度/易碎度修改

### 🔄 自动更新
- 启动时静默检查 GitHub Release
- 国内镜像下载加速（ghproxy）
- 断点续传 · 完整性校验 · 静默安装

</td>
</tr>
</table>

---

## 📥 安装方式

### Inno Setup 安装包（推荐）

从 v1.1.9 起使用 **Inno Setup** 打包，安装包自动完成：

| 特性 | 说明 |
|---|---|
| 程序注册 | 注册到「添加/删除程序」，支持系统卸载 |
| 快捷方式 | 自动创建开始菜单和桌面图标 |
| 版本升级 | 安装新版本时自动卸载旧版 |
| 自动更新 | 程序内检查更新 → 自动下载安装包 → 静默安装 |
| 安装路径 | 默认 `%LocalAppData%\Programs\EuroTruckSaveEditor` |

### 快捷键

| 快捷键 | 功能 |
|:---:|---|
| `Ctrl + B` | 浏览存档 |
| `Ctrl + S` | 保存修改 |

---

## 📂 存档位置

| 游戏 | 路径 |
|---|---|
| **ETS2** | `Documents\Euro Truck Simulator 2\profiles\<存档名>\save\1\game.sii` |
| **ATS** | `Documents\American Truck Simulator\profiles\<存档名>\save\1\game.sii` |

---

## 📋 更新日志

<details>
<summary><b>v3.1.5</b> — 🎨 HUD 全息终端侧边栏</summary>

- 侧边栏重构：四角 L 形霓虹角标 + 六边形网格点阵 + 对角线扫描线
- 菱形指示灯导航按钮，带编号前缀
- 2×2 终端状态面板（STATUS / MODE / ENC / SYS）
- 更新对话框升级为 QFluentWidgets 行业标准 Fluent Design
- 电路板风格分组分隔线

</details>

<details>
<summary><b>v3.1.4</b> — 🎨 UI 全面重写</summary>

- 玻璃拟态 + 霓虹渐变主题
- 无边窗圆角对话框设计
- 侧边栏导航重构
- 整体视觉升级

</details>

<details>
<summary><b>v3.1.3</b> — 🔧 自动更新修复</summary>

- 修复 Inno Setup 安装包自动更新：安装后自动启动新版
- 修复桌面图标空白问题
- 修复开始菜单文件夹名称无效错误
- 无边框圆角更新对话框

</details>

<details>
<summary><b>v3.1.2</b> — 🔧 自动更新机制</summary>

- Inno Setup 安装包静默更新
- ShellExecute UAC 提权安装
- 国内镜像下载加速

</details>

<details>
<summary><b>更早版本</b></summary>

- **v3.1.0** — Inno Setup 安装包支持
- **v3.0.0** — PySide6 + QFluentWidgets 全新 UI
- **v1.x** — 功能完善与 Bug 修复

</details>

---

## 💬 交流反馈

<div align="center">

[![QQ Group](https://img.shields.io/badge/QQ%E7%BE%A4-%E7%82%B9%E5%87%BB%E5%8A%A0%E5%85%A5-8b5cf6?style=for-the-badge&logo=tencentqq)](https://qm.qq.com/q/dtVBOPulCo)

</div>

---

## 🛡️ 安全声明

- 本工具**仅修改本地存档文件**，不注入游戏进程，不修改游戏内存
- ETS2 / ATS 为单机游戏，**无任何反作弊机制**
- 自动更新功能仅连接 GitHub Release API 获取版本信息和下载安装包
- 保存时自动备份原文件（`game.bak.sii`），随时可恢复
- 使用本工具产生的任何后果由用户自行承担，建议始终保留存档备份

---

<div align="center">

### ⚡ 社区爱好者作品 · 与 SCS Software 无任何关联 ⚡

*Made with 💜 for the trucking community*

</div>