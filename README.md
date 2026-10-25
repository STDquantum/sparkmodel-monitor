# Formula 1 车模目录与商品监控

采集 Spark、Looksmart、Minichamps 和 Carmodel（Burago）的 Formula 1 车模信息，整理商品属性、详情和图片，生成支持本地浏览与 GitHub Pages 发布的静态目录。项目提供商品搜索、条件筛选、图片查看、手动编辑、日期标注和钉钉通知功能。

采集程序与本地服务使用 Python 标准库，网页使用 HTML、CSS 和 JavaScript。

## 本地使用

在 `sparkmodel-monitor` 目录中操作。本地运行环境为 Python 3，GitHub Actions 使用 Python 3.12。

| 入口 | 用途 |
| --- | --- |
| `浏览目录.bat` | 启动本地服务，打开商品目录 |
| `管理商品与时间.bat` | 打开日期标注与商品管理页面 |
| `更新比美高.bat` | 采集 Carmodel（Burago）商品，生成详情、图片、目录及差异记录 |

本地服务运行依赖启动窗口。Windows 启动脚本的 Python 选择优先级为 `PYTHON_HOME`、`D:\conda\env3.10\python.exe`、系统 `py -3`。

终端入口：

```powershell
python scripts/serve_local.py --page index.html
```

| 页面 | 地址 | 用途 |
| --- | --- | --- |
| 商品目录 | <http://127.0.0.1:410/> | 搜索、筛选和查看商品 |
| 日期标注 | <http://127.0.0.1:410/annotate.html> | 进入目录编辑模式，填写 `published` 与 `shipped` 字段 |
| 商品管理 | <http://127.0.0.1:410/product-editor.html> | 商品编辑、属性填写、图片管理 |
| 差异记录 | <http://127.0.0.1:410/updates.html> | 查看商品字段与图片的比较结果 |

`python scripts/serve_local.py` 默认打开两个管理页面。`--port 8000` 指定服务端口，`--no-browser` 采用手动访问方式。

[商品目录](docs/index.html)与[差异记录](docs/updates.html)支持直接打开 HTML 文件浏览。商品管理的保存接口由本地服务提供。

## 目录功能

- 搜索商品名称、车型、年份、车手等商品文本。
- 按年份、车队、厂商、大奖赛、比例、Availability、样品及出货状态筛选。
- 按日期、大奖赛、车队、货号、比例、Availability 和样品排序，支持升序与降序。
- 查看商品属性、描述、来源链接、缩略图和大图。
- 图片查看支持滚轮缩放、拖动及双击缩放。
- 浏览器保存搜索、筛选和排序条件，清除按钮用于重置条件。

大奖赛筛选依赖年份选择，`OTHERS` 用于容纳其余分类。样品状态依据图片数量及来源类型判断；出货状态依据 `shipped` 字段判断。Availability 对应来源网站的商品属性。

## 商品编辑

商品管理页提供商品搜索、选择和“添加商品”入口。

| 字段 | 填写规则 |
| --- | --- |
| Year、Manufacturer、Scale、Product number、Availability | 必填；货号具有唯一性 |
| 商品名称 | 选填；默认名称由厂商、货号和年份组成 |
| 商品链接、商品描述 | 选填 |
| 其他商品详情 | 通过“＋ 添加详情项”填写；字段名具有唯一性，使用固定字段以外的名称 |

图片支持 PNG、JPEG、GIF、WebP，单张上限为 15 MB，单次添加上限为 30 张，本地服务单次请求体上限为 64 MiB。点击图片可查看大图，“保存商品”用于提交表单和图片操作，页面以“已保存”表示保存结果。

手动数据位于 `docs/manual-products.js`，上传图片位于 `docs/manual-images/`。目录合并使用手动属性、详情项及图片配置。手动图片具有展示优先级，图片去重依据 SHA-256 内容指纹，采集图片的删除配置也采用内容指纹。

## 日期字段

目录编辑模式提供 `published` 与 `shipped` 两个日期字段，填写格式为 `YYYY-MM-DD`。字段采用自动保存，空值显示为“无”。数据位于 `docs/product-times.js`，以货号为 key，由目录页面读取。

日期字段用于详情展示、卡片展示及排序。按 `shipped` 排序时，空值条目位于末尾，同组商品按相同方向的 `published` 排序。

日期保存支持两种方式：

- 本地服务：通过 `scripts/serve_local.py` 提供的接口保存。
- 浏览器文件写入：使用支持文件写入的 Chrome / Edge 打开 `docs/annotate.html`，点击“选择时间 JS，启用自动保存”，选择 `docs/product-times.js` 并授予写入权限。

## 数据采集

采集依赖来源网站与图片地址的网络访问。钉钉通知依赖机器人 Webhook。差异记录依赖 Git 仓库与有效提交。

### Carmodel（Burago）

本地入口为 `更新比美高.bat`，所需快照文件为 `data/state.json`。终端命令：

```powershell
python scripts/refresh_carmodel.py --build
```

| 参数 | 用途 |
| --- | --- |
| 默认参数 | 采集配置范围内的 Carmodel 商品，保存商品快照 |
| `--build` | 生成商品详情、图片、目录及差异记录 |
| `--resume` | 使用 `tmp/carmodel/` 中的检索缓存 |

Carmodel 使用 Encyclopedia（`enc=1`）检索，覆盖符合年份、品牌和车型条件的各类商品状态，支持分页与 Show all。商品以 Carmodel ID 去重，货号、比例和套装作为商品信息保存。`Catalogue` 对应目录收录状态，`Expected release` 保存来源提供的季度信息。

线上目录的数据来源为仓库中的 `data/state.json` 和 `docs/`。本地采集结果通过 Git 提交与推送发布。

### 监控、目录与差异记录

钉钉机器人配置使用环境变量：

```powershell
$env:DINGTALK_WEBHOOK = '钉钉机器人的完整 HTTPS Webhook 地址'
$env:DINGTALK_KEYWORD = '成绩'
python scripts/monitor.py
python scripts/catalog.py
python scripts/updates.py
```

三个脚本按代码块顺序执行，执行条件为各步骤成功。

| 脚本 | 职责 | 输出 |
| --- | --- | --- |
| `scripts/monitor.py` | 检索来源商品，比较列表、封面、Availability 和适用商品的 Shop 图库，发送钉钉通知 | `data/state.json` |
| `scripts/catalog.py` | 读取快照，采集详情与图片，生成商品目录并整理图片引用 | `docs/catalog.json`、`docs/catalog.js`、`docs/images/` |
| `scripts/updates.py` | 比较目录与 Git 基线，生成商品字段及图片的差异记录 | `docs/updates.json`、`docs/updates.js` |

钉钉通知覆盖初始化及商品差异，每类最多展开 20 件商品。通知成功是对应快照写入的条件。检索失败、详情抓取失败及空图库使用快照或目录中的对应数据，运行输出提供失败信息。

Carmodel 对 HTTP 401、403、429 采用来源级终止策略；临时网络错误与部分服务端错误的尝试上限为 3 次，请求超时为 20 秒，重试间隔为 2、4 秒。来源访问诊断入口为 `python scripts/carmodel_probe.py`，输出包括 HTTP 状态与商品卡片数。

差异记录的默认比较基线为 `HEAD`。指定提交或分支的命令：

```powershell
python scripts/updates.py --base <提交或分支>
```

### 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | 空 | 钉钉机器人 HTTPS Webhook，通知所需凭据，通过环境变量或 GitHub Secret 配置 |
| `DINGTALK_KEYWORD` | `成绩` | 与机器人配置一致的通知关键词 |
| `MINICHAMPS_ENABLED` | `true` | Minichamps 检索开关；`false` 使用快照中的对应数据 |
| `CARMODEL_ENABLED` | 脚本：`true`；Actions：`false` | Carmodel 采集开关；本地比美高入口使用 `true`，Actions 使用 `false`，读取仓库中的比美高数据 |
| `CATALOG_WORKERS` | `6` | 详情采集并发数，取正整数 |
| `PYTHON_HOME` | 空 | Windows 启动脚本使用的 Python 目录 |

## 商品来源与范围

检索范围由 `scripts/monitor.py` 和 `scripts/carmodel.py` 中的配置定义。

| 来源 | 2025 赛季车型 | 2026 赛季车型 |
| --- | --- | --- |
| Spark | C45、A525、FW47、MCL39、W16、RB21、VF-25、VCARB 02、AMR25 | VF26、MAC26、FW48、AMR26、A526、W17、R26、MCL40、VCARB03、RB22 |
| Sparkmodelshop | VCARB 02、RB21 | SF-26，用于 Looksmart 图片匹配 |
| Looksmart | SF-25 | SF-26 |
| Minichamps | 2025 Formula 1 分类 | W17、VF-26、AMR26、VCARB 03、MAC-26、A526、Audi R26、RB22、FW48、MCL40、SF-26 |
| Carmodel（Burago） | AMR25、A525、RB21、SF-25、MCL39、W16 | AMR26、A526、SF-26、RB22、MCL40、W17、VCARB-03、VF-26、FW48、MAC-26、R26 |

Spark 与 Sparkmodelshop 按货号去重，Spark 官网条目具有优先级。Shop 补充范围为符合配置条件的 2025 Spark 商品。Spark 的 2026 商品按标题年份与比例规则筛选。

2026 Looksmart 按货号匹配 Sparkmodelshop，图片优先使用匹配的 Shop 图库，备选来源为官网图片。名称、属性和描述来自 Looksmart 官网。图库以封面为首图，按内容去重。

## GitHub Actions 与 Pages

### 工作流配置

项目内容作为 GitHub 仓库根目录，工作流配置位于 `.github/workflows/monitor.yml`。

在仓库 **Settings → Secrets and variables → Actions** 中配置：

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | Secret | 机器人完整 Webhook 地址 |
| `DINGTALK_KEYWORD` | Variable，选填 | 通知关键词，默认值为 `成绩` |

`Monitor Spark Models` 工作流支持定时触发与手动 **Run workflow**，调度间隔为 10 分钟，单次任务上限为 30 分钟，同组任务采用排队方式。

云端采集来源为 Spark、Looksmart 和 Minichamps，Carmodel 数据取自仓库。目录与差异记录的生成条件为 `data/state.json` 与仓库存在差异。工作流将 `data/state.json` 与 `docs/` 中的差异提交并推送，所需权限为 `contents: write`，提交行为受分支保护规则约束。

`Carmodel connectivity probe` 工作流的 PR 检查范围为脚本和数据路径。手动诊断提供网站访问测试，`browser` 选项提供浏览器式连接与 Chromium 测试。

### 静态站点配置

GitHub Pages 的发布内容为仓库中的完整 `docs/` 目录。在 **Settings → Pages** 选择 **Deploy from a branch**，指定项目分支和 `/docs` 目录，页面提供站点地址。

手动维护数据的发布文件包括 `docs/manual-products.js`、`docs/manual-images/` 和 `docs/product-times.js`。GitHub Pages 提供目录浏览，商品写入通过本地服务完成。

## 文件说明

| 路径 | 用途 |
| --- | --- |
| `scripts/monitor.py` / `data/state.json` | 商品检索、通知与快照 |
| `scripts/paths.py` | 项目路径配置 |
| `scripts/catalog.py` | 详情采集、图片下载与目录生成 |
| `scripts/carmodel.py` / `scripts/refresh_carmodel.py` | Carmodel 解析与 Burago 本地采集 |
| `scripts/carmodel_probe.py` | Carmodel 网站访问诊断 |
| `scripts/updates.py` | Git 基线比较与差异记录生成 |
| `浏览目录.bat` / `管理商品与时间.bat` / `更新比美高.bat` | Windows 操作入口 |
| `scripts/serve_local.py` / `scripts/run_local.bat` | 本地服务与共享启动逻辑 |
| `scripts/manual_products.py` | 手动商品合并、校验与图片指纹管理 |
| `docs/index.html` / `docs/updates.html` | 商品目录与差异记录页面 |
| `docs/annotate.html` / `docs/product-editor.html` | 日期标注入口与商品管理页面 |
| `docs/catalog.json` / `docs/catalog.js` | 采集目录与网页数据 |
| `docs/updates.json` / `docs/updates.js` | 差异记录与网页数据 |
| `docs/images/` | 采集图片 |
| `docs/manual-products.js` / `docs/manual-images/` | 手动商品数据与上传图片 |
| `docs/product-times.js` | 以货号索引的日期字段 |
| `.github/workflows/monitor.yml` | 自动采集与提交配置 |
| `tests/` | 本地测试，Git 忽略规则覆盖此目录 |
