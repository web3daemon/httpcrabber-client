<div align="center">

<img src="assets/logo.svg" alt="httpcrabber" width="880">

<br>

**用于逆向分析 Web API 的网络层流量拦截工具。**
对页面内的 JavaScript 防护完全隐形 —— 因为它从不进入页面。

[English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · **中文**

[![CI](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml/badge.svg)](https://github.com/web3daemon/httpcrabber-client/actions/workflows/ci.yml)
[![Python 3.11+](assets/badge-python.svg)](https://www.python.org/)
[![平台 Windows · macOS · Linux](assets/badge-platform.svg)](#环境要求)
[![许可证 GPL-3.0](assets/badge-license.svg)](LICENSE)
[![基于 mitmproxy](assets/badge-mitmproxy.svg)](https://mitmproxy.org/)

</div>

---

```
┌──────────────────────────── 🦀 SESSION LIVE ─────────────────────────────┐
│                                                                          │
│    Session  TARGET RECON                                                 │
│   Upstream  socks5://user:****@1.2.3.4:1080                              │
│  mitmproxy  127.0.0.1:8080                                               │
│     Folder  LOGS/target_recon                                            │
│                                                                          │
│   ⠸  LIVE INTERCEPT                                                      │
│   14:22:07  GET    200  https://cdn.target.com/static/js/main.a3f1c8…    │
│   14:22:07  POST   403  https://api.target.com/v2/auth/challenge         │
│   14:22:08  GET    304  https://target.com/assets/app.css                │
│   14:22:08  POST   200  https://api.target.com/v2/graphql                │
│   14:22:09  WS     →    wss://realtime.target.com/socket                 │
│   14:22:10  GET    500  https://api.target.com/v2/telemetry/collect      │
│   14:22:11  ERR    ···  https://blocked.tracker.io/beacon                │
│   14:22:12  DELETE 204  https://api.target.com/v2/session                │
│                                                                          │
│   ● REQ 1478 ● RESP 1443 ● WS 12 ● JS 38 ● ERR 2   ▂▆█▄▂▁▁▄  03:41       │
│                                                                          │
│        Close Chrome or press Ctrl+C to finish and save the session.      │
└──────────────────────────────────────────────────────────────────────────┘
```

<details>
<summary><b>目录</b></summary>

- [为什么需要它](#为什么需要它)
- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令行](#命令行)
- [代理格式](#代理格式)
- [保存的内容](#保存的内容)
- [工作原理](#工作原理)
- [安全提示](#-安全提示)
- [负责任地使用](#负责任地使用)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

</details>

## 为什么需要它

浏览器开发者工具是可以被检测到的。反爬虫 JavaScript（Kasada、Cloudflare、Vercel BotID）
会例行检查是否附加了调试器、开发者面板是否打开，以及网络栈是否在页面内部被篡改过。

**httpcrabber 运行在这一切之下。** 它是基于 [mitmproxy](https://mitmproxy.org/) 的 HTTPS
代理：流量是在链路上被捕获的，而不是在页面里。从 JavaScript 的视角看，那里什么都没有。

## 功能特性

| | |
|---|---|
| 💚 **动画黑客风 CLI** | 矩阵字符雨、渐变故障横幅、打字机效果、真实的 `[ OK ]` 状态行、真实等待时的加载动画 |
| 📡 **实时拦截信息流** | 实时显示请求，方法与状态码彩色高亮，计数器，流量迷你折线图 |
| 📊 **会话分析** | 结束时显示热门主机、方法与状态分布、时长与转储大小 |
| 🧅 **支持任意上游代理** | `socks5` / `socks5h` / `socks4` / `http` / `https`，带或不带认证，支持所有常见写法 |
| 🗂 **每个会话独立文件夹** | 网络转储与全部脚本放在一起，可整体归档或分享 |
| 📜 **完整抓取 JavaScript** | 外部打包文件与内联 `<script>` 块，完整保存并按 SHA-256 去重 |
| 🌐 **Chrome 自动启动** | 通过代理启动并使用独立配置；也可用 `--no-browser` 使用你自己的浏览器 |
| 🔐 **自动配置 CA 证书** | 首次运行时自动检查并安装证书，支持 Windows、macOS 与 Linux |
| ⌨️ **可脚本化** | 每个提问都有对应参数；全部传入则不再询问 |
| ⏹ **安全退出** | 关闭 Chrome *或* 按 `Ctrl+C` 均可结束，两种情况下转储都会保存、子进程都会被清理 |
| 🌍 **双语界面** | 俄语或英语，启动时选择或通过 `--lang` 指定 |

## 环境要求

- **Python 3.11+**
- **Google Chrome** 或 **Chromium**（使用 `--no-browser` 时可省略）

| 操作系统 | 浏览器查找 | CA 证书安装 |
|---|---|---|
| **Windows** | Program Files、LocalAppData | 通过 `certutil -user` 写入用户 Root 存储 —— Windows 会弹出一次确认对话框 |
| **macOS** | `/Applications`、`~/Applications` | 通过 `security add-trusted-cert` 写入登录钥匙串 —— macOS 会询问一次密码 |
| **Linux** | `PATH` 中的 `google-chrome`、`chromium` | 通过 **libnss3-tools** 的 `certutil` 写入 NSS 数据库 `~/.pki/nssdb`（`sudo apt install libnss3-tools`）—— Chrome 读取的正是它。Firefox 使用独立存储，请在其中通过 http://mitm.it 安装 |

在任何系统上都可通过 `HTTPCRABBER_BROWSER=/path/to/chrome` 覆盖浏览器查找。

## 安装

```bash
pip install git+https://github.com/web3daemon/httpcrabber-client.git
httpcrabber --version
```

或从克隆的仓库安装，便于开发：

```bash
git clone https://github.com/web3daemon/httpcrabber-client.git
cd httpcrabber-client
python -m venv .venv && source .venv/bin/activate     # Windows 上使用 .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

完全不安装？在克隆目录中直接运行 `python run.py` 即可。

## 快速开始

```bash
httpcrabber
```

工具只会询问三件事，其余全部自动完成：

1. **语言** —— 俄语或英语
2. **上游代理** —— 任意格式粘贴即可，或直接按 <kbd>Enter</kbd> 使用直连
3. **会话名称** —— 例如 `TARGET RECON`

随后会显示会话简报，在需要时安装 CA 证书，通过代理启动 Chrome，并把所有内容写入会话
文件夹。正常浏览即可 —— 每一个请求、响应、WebSocket 帧和脚本都会被捕获。关闭 Chrome
（或按 <kbd>Ctrl+C</kbd>）结束会话，你将看到分析面板与文件夹路径。

```
┌─────────────────────────────── ✓ SESSION FINISHED ────────────────────────────────┐
│                                                                                   │
│    Requests  1478        TOP HOSTS                                                │
│   Responses  1443        api.target.com       ██████████████ 612                  │
│   WebSocket  12          cdn.target.com       █████████ 380                       │
│  JS scripts  38          static.target.com    █████ 214                           │
│      Errors  2           tracker.io           ██ 96                               │
│    Duration  03:41                                                                │
│                          Methods  GET 1201 · POST 260 · OPTIONS 17                │
│                          Status   2xx 1380 · 3xx 12 · 4xx 51                      │
│                                                                                   │
│      Folder  LOGS/target_recon                                                    │
│        Dump  2.31 MB                                                              │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## 命令行

每个提问都有对应参数。全部传入后 httpcrabber 不会再询问任何内容，便于脚本调用。

```bash
httpcrabber --lang en --session "target recon" --proxy socks5://user:pass@1.2.3.4:1080
httpcrabber -l en -s quick --direct --no-browser          # 使用你自己的浏览器 / 设备
httpcrabber --no-anim                                      # 纯文本输出，无动画
```

| 参数 | 含义 |
|---|---|
| `-l, --lang {ru,en}` | 界面语言 |
| `-s, --session NAME` | 会话名称 → `LOGS/<name>/` |
| `-p, --proxy PROXY` | 上游代理，任意[格式](#代理格式) |
| `--direct` | 不使用上游代理 |
| `--port PORT` | mitmproxy 监听端口（默认 `8080`，被占用时取下一个空闲端口） |
| `-o, --output DIR` | 会话保存目录（默认 `./LOGS`） |
| `--no-browser` | 不启动 Chrome —— 将任意浏览器或设备指向 `127.0.0.1:<port>` |
| `--no-anim` | 关闭动画 |
| `-V, --version` | 显示版本 |

## 代理格式

支持所有常见写法。留空并按 <kbd>Enter</kbd> 表示直连。

```
host:port
host:port:user:pass
user:pass@host:port
socks5://user:pass@host:port
http://host:port
https://user:pass@host:port
```

协议：`http`、`https`、`socks5`、`socks5h`、`socks4`。界面中密码会被掩码显示。

## 保存的内容

每个会话都是一个自包含的文件夹：

```
LOGS/
└── target_recon/
    ├── target_recon.jsonl                     # 网络转储
    └── js/
        ├── index.json                         # 清单：url、文件、sha256、大小、命中次数
        ├── cdn.target.com/
        │   └── main.a3f1c8d4.js               # 外部脚本
        └── target.com/
            └── inline/inline_0001.e5f6a7b8.js # 内联 <script> 块
```

若同名会话已存在，会追加 `_2`、`_3` …… —— **任何内容都不会被覆盖。**

### 网络转储

每行一个 JSON 对象，包含 `event` 字段：
`request` · `response` · `ws_open` · `ws_msg` · `ws_close` · `error`。
每条记录都会立即写入磁盘，即使崩溃或被强制终止也不会丢失数据。

### 抓取的 JavaScript

- **脚本完整保存。** `.jsonl` 中的响应体会在 200 KB 处截断，但 `js/` 目录中的文件是完整
  源码 —— 5 MB 的压缩打包文件也会被完整保存。
- **依据 SHA-256 自动去重。** 被请求一百次的同一个打包文件只存储一份，清单中记为 `hits: 100`。
- **从 HTML 中提取内联脚本。** 带 `src=` 的标签会被跳过（它们会作为独立请求到达），
  `application/ld+json` 与 `text/template` 同样跳过 —— 它们不是代码。
- 文件名包含内容的短哈希，因此同一个 `app.js` 的不同构建版本不会相互覆盖。

## 工作原理

```
  Chrome ──▶ mitmproxy ──▶ pproxy 桥接 ──▶ 你的上游代理 ──▶ 目标站点
             (捕获流量)     (协议适配)
```

mitmproxy 原生仅支持 `http`/`https` 上游代理。为了让 **SOCKS5** 也能透明工作，httpcrabber
会启动一个本地 [pproxy](https://github.com/qwj/python-proxy) 桥接：它与 mitmproxy 之间使用
HTTP 通信，与你的代理之间使用任意协议。两跳都走本地回环，因此开销可以忽略不计。

```
src/httpcrabber/
  cli.py       参数、交互提问、main()
  session.py   编排：桥接 → mitmproxy → CA → 浏览器 → 实时循环
  capture.py   mitmproxy 插件：JSONL 转储、JS 收集、实时统计
  proxy.py     上游代理解析                  bridge.py   pproxy 桥接
  ca.py        各系统的 CA 安装              browser.py  各系统的 Chrome 查找
  ui.py        动画、面板、信息流            i18n.py     界面文本
```

## ⚠️ 安全提示

**捕获的流量包含有效凭据。** 会话转储通常会包含你在该会话期间访问过的所有站点的
`Cookie`、`Set-Cookie`、`Authorization` 请求头、API 密钥与令牌。

- `LOGS/` 与 `*.jsonl` 已在 [`.gitignore`](.gitignore) 中排除 —— **请保持这样**。
- 在未经检查之前，切勿提交、上传或分享会话转储。
- 请把会话文件夹当作你的密码管理器导出文件来对待。因为它实际上就是。
- 本工具会安装一个本地生成的根 CA。使用完毕后如何移除，请参阅 [SECURITY.md](SECURITY.md)。

## 负责任地使用

本工具适用于安全研究、API 调试，以及针对你所拥有或已获授权测试的系统开展的互操作性工作。
你有责任遵守适用法律、所访问站点的服务条款，以及你可能接触到的任何第三方数据的隐私要求。
请勿用于未经许可访问他人系统。

## 参与贡献

欢迎提交 Issue 与 Pull Request —— 环境搭建、约定以及如何添加语言请参阅
[CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请通过 [SECURITY.md](SECURITY.md) 报告。

```bash
ruff check src tests run.py && pytest
```

## 许可证

[GNU General Public License v3.0](LICENSE) —— 完整条款见许可证文件。
