# Formula 1 车模商品目录

基于 Python 标准库的 Formula 1 车模采集工具，提供商品检索、钉钉通知和静态目录。GitHub Actions 工作流配置 cron 与手动触发器，目录文件可用于 GitHub Pages。

## 功能

- 从 Spark、Looksmart 和 Minichamps 检索 Formula 1 车模商品。
- 按商品 ID 汇总检索结果，记录条目、封面图片链接和 Availability 字段。
- 通过钉钉机器人发送 Markdown 状态通知。
- 采集商品属性与图片，生成 JSON 数据和静态网页。
- 浏览商品条目与图片记录，并在目录页面搜索、筛选、排序和查看商品图片。

## 商品检索范围

| 来源 | 检索范围 |
| --- | --- |
| Spark | 2025 车型关键词：C45、A525、FW47、MCL39、W16、RB21、VF-25、VCARB 02、AMR25；2026 车型关键词：VF26、MAC26、FW48、AMR26、A526、W17、R26、MCL40、VCARB03、RB22 |
| Looksmart | SF-25、SF-26 搜索结果 |
| Minichamps | 2025 Formula 1 分类；2026 车型关键词：W17、VF-26、AMR26、VCARB 03、MAC-26、A526、Audi R26、RB22、FW48、MCL40 |

各来源采用其检索页分页结果。Spark 的 2026 条目要求标题包含 `2026`，并排除 `1:5` 比例；Minichamps 与 Looksmart 的车型筛选规则定义于 `monitor.py`。

## 处理流程

1. `monitor.py` 请求商品检索页、读取分页并整理商品列表。
2. 程序按商品 ID 汇总各来源条目，将商品名称、链接、封面图片地址、Availability 和来源信息写入 `state.json`。
3. 钉钉通知涵盖商品 ID 收录状态、封面链接与 Availability；`monitor.py` 按通知规则输出 Markdown 消息。
4. `catalog.py` 采集商品详情与图片，生成目录 JSON 和本地图片文件；自动化配置包含此脚本步骤。
5. `updates.py` 生成商品与图片信息数据，相关页面文件位于 `docs/`。
6. `.github/workflows/monitor.yml` 配置 `state.json` 与 `docs/` 的 Git 提交；GitHub Pages 使用 `docs/` 提供静态目录。

钉钉消息包含商品名称、商品链接、货号、比例和状态信息。每类消息至多列出 20 件商品。

## 静态商品目录

`docs/index.html` 使用 `docs/catalog.json` 展示商品。商品卡片呈现名称、图片、比例、年份、货号与 Availability；商品详情区域呈现其余属性和描述。商品名称链接指向来源站点。

目录支持以下操作：

- 关键词搜索：商品名称、车型、年份、车手及商品数据中的其他文本。
- 按年份、车队、厂商、大奖赛、比例、Availability 和样品筛选。
- 按大奖赛、车队、货号、比例、Availability 和样品数量排序，并选择升序或降序。
- 清除筛选与排序条件。
- 浏览商品图片、切换图片、选择缩略图、滚轮缩放和拖动图片；双击图片切换 1 倍与 2 倍缩放。

大奖赛筛选条件由赛季年份和赛事名称组成。无法匹配赛事规则的商品归入 `OTHERS`。样品筛选以商品图片数量和来源类型为依据。搜索、筛选与排序设置存储于浏览器本地存储。

`docs/updates.html` 展示商品条目与图片记录；记录可链接至目录中的对应商品。`catalog.py` 把商品图片保存至 `docs/images/`，网页引用仓库内的图片文件。

## 文件结构

| 路径 | 用途 |
| --- | --- |
| `monitor.py` | 请求检索页、汇总商品列表并发送钉钉消息 |
| `catalog.py` | 采集商品详情、下载图片、整理目录数据并清理未引用图片 |
| `updates.py` | 生成商品与图片记录数据 |
| `state.json` | 商品 ID、来源地址与商品状态记录 |
| `docs/index.html` | 商品目录页面与交互逻辑 |
| `docs/catalog.json` | 商品目录数据 |
| `docs/catalog.js` | 商品数据脚本，支持本地文件预览 |
| `docs/images/` | 商品图片文件 |
| `docs/updates.html` | 商品与图片信息页面 |
| `docs/updates.json` | 商品与图片信息数据 |
| `docs/updates.js` | 信息数据脚本，支持本地文件预览 |
| `.github/workflows/monitor.yml` | GitHub Actions 自动化配置 |
| `serve_docs_410.bat` | Windows 本地 HTTP 预览入口，监听 `127.0.0.1:410` |

`catalog.json` 包含商品数组 `products`。商品记录包含 `id`、`name`、`url`、`images`、`properties`、`description`、`brand`、价格、重量、尺寸和 Availability 等字段；字段内容依来源而定。

## 运行环境

- Python 3.12 或兼容版本。
- Git，用于运行 `updates.py` 和 GitHub Actions 提交。
- 网络访问，用于商品检索、图片下载和钉钉 Webhook 请求。

Python 脚本只使用标准库。静态页面不依赖 Node.js、数据库或服务端框架。

## GitHub Actions 配置

把本目录内容置于 GitHub 仓库根目录，并提交 `.github/workflows/monitor.yml`。

在仓库 `Settings` → `Secrets and variables` → `Actions` 配置：

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | Secret | 钉钉自定义机器人的完整 HTTPS Webhook 地址 |
| `DINGTALK_KEYWORD` | Variable，可选 | 机器人配置的自定义关键词；默认值为 `成绩` |

工作流名称为 `Monitor Spark Models`。触发配置包含 cron 表达式 `*/10 * * * *` 和手动运行入口。单个任务的运行上限为 30 分钟，任务具有仓库内容写入权限（`contents: write`）。仓库分支保护规则适用于工作流提交。

## GitHub Pages 配置

在仓库 `Settings` → `Pages` 中设置：

1. Source：`Deploy from a branch`。
2. Branch：包含项目文件的默认分支。
3. Folder：`/docs`。
4. 保存设置，使用 GitHub Pages 显示的站点地址浏览目录。

## 本地运行与预览

在 PowerShell 中进入 `sparkmodel-monitor` 目录，设置钉钉 Webhook 并运行监控脚本：

```powershell
$env:DINGTALK_WEBHOOK='钉钉机器人的完整 HTTPS 地址'
$env:DINGTALK_KEYWORD='机器人设置的关键词'
python monitor.py
```

`DINGTALK_KEYWORD` 为可选环境变量。`catalog.py` 使用 `state.json` 中的商品 ID 获取商品详情和图片。`updates.py` 需要 Git 仓库及有效的 `HEAD` 提交，并读取其中的目录资料。

使用 Python 提供静态页面：

```powershell
python -m http.server 8000 --directory docs
```

浏览器访问 `http://localhost:8000/`。Windows 用户也可运行 `serve_docs_410.bat`，访问 `http://127.0.0.1:410/`。部分浏览器限制本地文件读取 JSON；HTTP 服务可提供页面和 JSON 文件。

## 配置与安全

商品关键词和检索地址定义于 `monitor.py`。目录处理包含来源地址验证：`state.json` 中的地址须与脚本配置一致。

钉钉 Webhook 通过 `DINGTALK_WEBHOOK` 环境变量或 GitHub Actions Secret 提供。程序要求 HTTPS 地址，主机名属于 `dingtalk.com`。请勿把 Webhook 或访问凭证写入代码、README、`state.json` 或 Git 提交。

## 常见问题

- **没有钉钉消息**：检查 `DINGTALK_WEBHOOK` 的 HTTPS 地址和 GitHub Secret，以及 `DINGTALK_KEYWORD` 与机器人配置的一致性。
- **Actions 无法提交**：检查仓库内容写入权限和默认分支保护规则。
- **目录未显示商品或图片**：检查 `docs/catalog.json`、`docs/catalog.js` 和 `docs/images/`，并通过本地 HTTP 服务或 GitHub Pages 访问。
- **目录脚本提示来源地址不匹配**：核对 `monitor.py` 的检索配置与 `state.json` 中的 `sources`。
- **记录页图片无法显示**：记录页引用 `docs/images/` 中的图片文件；对应图片文件缺失导致图片无法显示。
