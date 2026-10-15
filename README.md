# Formula 1 车模商品目录

## 本地手动商品管理

双击 `start_local.bat`，启动同一个本地服务并同时打开商品管理页与时间标注页，或在已启动的时间标注页点击“添加 / 修改商品”。如果本地服务已经运行，直接打开 `http://127.0.0.1:410/product-editor.html`，无需再次启动。

左侧搜索并选择任意已有商品可进行修改；点击“添加商品”创建新条目。Year、Manufacturer、Scale、Product number、Availability 必填，其中年份、比例和 Availability 使用选框。名称、链接和描述可选，名称留空时根据厂商、货号、年份生成。货号不能与其他商品重复。

“其他商品详情”区域点击“＋ 添加详情项”可逐项增加字段名称和内容，点击行末 × 删除。修改已有商品时会带出其现有详情项，可继续修改或删除；字段名称不能重复，也不能覆盖上方固定字段。保存后在主网页商品详情展示，手动修改与删除在自动采集后仍保留。

可多选上传 PNG、JPEG、GIF、WebP 图片，每张最多 15 MB，每次最多添加 30 张。点击图片查看大图，点击“删除图片”移除，最后点击“保存商品”统一保存。修改成功后保持滚动位置，刷新主网页即可看到结果。

手动商品与属性修改保存于 `docs/manual-products.js`，手动图片保存在 `docs/manual-images/`。自动采集只更新自身商品与 `docs/images/`，不会覆盖手动修改或删除手动图片。手动图片优先保留，自动图片与手动图片按 SHA-256 文件内容指纹去重；内容有差异时均保留。手动删除的自动图片也按指纹记录，即使采集后文件名变化，相同内容仍不会重新出现。发布目录时一起提交手动数据 JS 和图片目录即可。

商品管理页通过本地服务写入文件；直接双击 HTML 可以浏览表单，但保存请使用本地启动入口。

## 本地发布时间与出货时间标注

双击 `start_local.bat`，浏览器会同时打开商品管理页和本地标注页（`http://127.0.0.1:410/annotate.html`）。保持启动窗口运行。标注页复用主目录的布局、筛选、排序和大图浏览；每个有货号的商品都有“添加 / 修改时间”按钮。日期统一为 `YYYY-MM-DD`，每次更改自动保存，清空日期表示“无”。请确认弹窗显示“已保存”后关闭。

所有标注统一保存在 `docs/product-times.js`，货号为唯一 key，值包含 `published`（发布时间）和 `shipped`（出货时间）。主网页通过脚本直接读取，本地启动和双击 HTML 均可使用，修改后刷新主网页即可。采集程序不会覆盖该文件。发布主网页时提交这一份 JS 即可带上标注。

主网页在商品详情最上方展示两个时间，缺失显示“无”。选择发布时间或出货时间排序后，两个时间移到卡片信息最下方。出货时间缺失的商品在升序和降序时均位于末尾，再按同方向的发布时间排序。出货状态筛选以是否填写出货时间为准。

也可以直接打开 `docs/annotate.html`：Chrome / Edge 中先点击“选择时间 JS，启用自动保存”，选择 `docs/product-times.js` 并授权写入，此后修改自动写入文件。直接文件模式也只更新同一份 JS，刷新主网页即可读取最新时间。其他静态服务器仅支持浏览，不支持保存，请使用上述启动入口。

基于 Python 标准库的 Formula 1 车模采集工具，提供商品检索、钉钉通知和静态目录。GitHub Actions 工作流配置 cron 与手动触发器，目录文件可用于 GitHub Pages。

## 功能

- 从 Spark、Looksmart、Minichamps 和 Carmodel（Burago）检索 Formula 1 车模商品。
- 按商品 ID 汇总检索结果；Spark 与 Sparkmodelshop 按货号去重，Spark 官网优先，记录条目、封面图片链接和 Availability 字段。
- 通过钉钉机器人发送 Markdown 状态通知。
- 采集商品属性与图片，生成 JSON 数据和静态网页。
- 浏览商品条目与图片记录，并在目录页面搜索、筛选、排序和查看商品图片。

## 商品检索范围

| 来源 | 检索范围 |
| --- | --- |
| Spark | 2025 车型关键词：C45、A525、FW47、MCL39、W16、RB21、VF-25、VCARB 02、AMR25；2026 车型关键词：VF26、MAC26、FW48、AMR26、A526、W17、R26、MCL40、VCARB03、RB22 |
| Sparkmodelshop（补充） | 2025 VCARB 02、RB21；从搜索卡片读取货号，仅官网未收录的货号进入目录并采集详情和图片 |
| Looksmart | SF-25、SF-26 搜索结果 |
| Minichamps | 2025 Formula 1 分类；2026 车型关键词：W17、VF-26、AMR26、VCARB 03、MAC-26、A526、Audi R26、RB22、FW48、MCL40、SF-26 |

各来源采用其检索页分页结果。Spark 的 2026 条目要求标题包含 `2026`，并排除 `1:5` 比例；Minichamps 与 Looksmart 的车型筛选规则定义于 `monitor.py`。

Sparkmodelshop 独立解析 Shopware 搜索卡片的属性表与库存文字，商品详情解析其属性、描述和原尺寸图库。补充条目要求年份为 2025、厂商为 Spark；货号去重在失败抓取的旧快照恢复后进行，仍优先保留官网记录。它不会替换官网商品的图片或详情。

2026 年 Looksmart 商品的封面和全部详情图优先使用 Sparkmodelshop：每次监控从 SF-26 搜索按货号匹配商品，并读取其详情图库，包含以后新加入的货号。匹配后仅使用完整 Shop 图库，不混入 LS 官网图库；Shop 封面放在首位，按文件内容去重；官网商品名称、属性和描述继续保留。商品详情自动展示 Shop 商品页链接。2025 Looksmart、Spark 和 Minichamps 不受影响。商店无匹配货号时继续检测 LS 官网封面变化并更新官网图库；商店请求失败时保留上次成功的 Shop 图库。封面和商品页记录于 `cover_source`、`cover_url`、`cover_product_url`，图库记录于 `shop_image_urls`，目录的 `image_source` 为 `sparkmodelshop`；已匹配商品的封面变化仅比较 Shop 封面地址，忽略其 LS 官网图片变化；未匹配商品仍比较 LS 官网封面地址；图片时间戳不参与变更判断，Shop 图库新增图片也会触发目录更新。

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

## Burago / Carmodel

`carmodel.py` 独立解析 Carmodel 搜索卡片、商品属性表、Product 结构化数据与原尺寸 fancybox 图库。2025 搜索 AMR25、A525、RB21、SF-25、MCL39、W16；2026 搜索 AMR26、A526、SF-26、RB22、MCL40、W17、VCARB-03、VF-26、FW48、MAC-26、R26。每词添加 `burago F1` 前缀，R26 另加 `Audi` 后缀，结果标题必须包含对应年份。

每个关键词同时抓取普通搜索和 Coming soon，并跟随 Show all 和分页链接；按 Carmodel 商品 ID 去重，保留不同货号、比例与套装。Coming soon 单独保留状态，预计到货季度存入 Expected release。图片重新读取商品详情页完整图库，以文件内容去重后保存到本地。会话 Cookie 用于处理网站语言与货币重定向。任一关键词抓取失败时保留该关键词上次成功的数据。

`carmodel-coverage.json` 记录最近一次人工全量核对的各词数量。可运行 `python refresh_carmodel.py` 只刷新 Burago 快照，再运行 `python catalog.py` 和 `python updates.py` 更新目录。
