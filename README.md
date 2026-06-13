<div align="center">

# 📁 群文件自动归档

<i>根据文件名自动将群文件移动到对应文件夹</i>

![License](https://img.shields.io/badge/license-AGPL--3.0-green?style=flat-square)
![Version](https://img.shields.io/badge/version-v1.0-blue?style=flat-square)
![AstrBot](https://img.shields.io/badge/framework-AstrBot-ff6b6b?style=flat-square)

</div>

## 简介

一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的群文件管理插件，能够根据文件名自动识别软件名称，并将文件移动到对应的文件夹中。

**示例：**

| 文件名 | 提取的软件名 | 目标文件夹 |
|--------|-------------|-----------|
| `QAuxv-v1.6.0.apk` | `QAuxv` | `Auxiliary（QQ TIM模块）` |
| `TCQT-3.6.4.apk` | `TCQT` | `TCQT（QQ模块）` |
| `模了个块_5.4.apk` | `模了个块` | `模了个块（QQ TIM模块）` |

---

## 安装

1. 下载本插件
2. 放入 `data/plugins/` 目录
3. 重启 AstrBot

---

## 配置

在 AstrBot 后台配置映射规则，格式：`关键词=文件夹名`
QAuxv=Auxiliary（QQ TIM模块）
TCQT=TCQT（QQ模块）
模了个块=模了个块（QQ TIM模块）

---

## 指令

| 指令 | 别名 | 说明 |
|------|------|------|
| `/fm` | `/归档` | 扫描根目录文件并归档 |
| `/fm all` | - | 扫描所有文件（包括文件夹内） |
| `/fmrules` | `/归档规则` | 查看映射规则 |
| `/fmtest` | `/测试归档` | 测试文件名提取 |

---

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

---

<div align="center">

**如果对你有帮助，欢迎 ⭐ Star！**

</div>
