<div align="center">

# 📁 群文件自动归档

<i>🤖 根据文件名自动将群文件移动到对应文件夹</i>

![License](https://img.shields.io/badge/license-AGPL--3.0-green?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white)
![AstrBot](https://img.shields.io/badge/framework-AstrBot-ff6b6b?style=flat-square)

</div>

## 📖 简介

一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的群文件管理插件，能够根据文件名自动识别软件名称，并将文件移动到对应的文件夹中。

### 工作原理

插件会从文件名中提取软件名（第一个 `_` 或 `-` 之前的部分），然后与配置的文件夹规则进行匹配。

**示例：**

| 文件名 | 提取的软件名 | 匹配的文件夹 |
|--------|-------------|-------------|
| `模了个块_5.4.apk` | `模了个块` | `模了个块（QQ TIM模块）` |
| `QAuxv-v1.6.0.apk` | `QAuxv` | `QAuxiliary（QQ TIM模块）` |
| `TCQT-3.6.4-release.apk` | `TCQT` | `TCQT（QQ模块）` |

---

## ✨ 功能特性

- 🔍 **智能识别** - 自动从文件名中提取软件名称
- 📁 **自动归档** - 根据规则将文件移动到对应文件夹
- 🛠️ **自定义规则** - 支持自定义关键词到文件夹的映射
- 🧪 **测试模式** - 测试文件名提取效果，不会实际移动
- 📊 **详细报告** - 移动完成后发送结果报告
- 🔄 **兼容性** - 同时支持 NapCat 和 LLOneBot

---

## 💿 安装

1. 下载本插件的完整文件夹
2. 放入 AstrBot 的 `data/plugins/` 目录下
3. 重启 AstrBot

---

## ⚙️ 配置

在 AstrBot 后台 → 插件 页面找到本插件进行设置。

### 文件夹规则

支持两种配置格式：

#### 格式1：简写格式

```json
[
    "TCQT（QQ模块）",
    "模了个块（QQ TIM模块）"
]