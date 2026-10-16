# Formula 1 车模目录与商品监控

采集 Spark、Looksmart、Minichamps 和 Carmodel（Burago）的 Formula 1 车模信息，保存商品详情与图片，并生成可本地浏览、可部署到 GitHub Pages 的静态目录。支持钉钉变化通知、手动添加和修改商品，以及发布时间和出货时间标注。

采集脚本与本地服务只使用 Python 标准库；网页无需安装 Node.js、数据库或前端构建工具。

## 快速开始

以下操作均在本项目目录 `sparkmodel-monitor` 中进行。

### 浏览现有目录

直接打开 [`docs/index.html`](docs/index.html) 即可浏览已生成的商品与本地图片；[`docs/updates.html`](docs/updates.html) 展示商品和图片的更新记录。

也可以启动本地服务，只打开目录页：

```powershell
python serve_local.py --page index.html
```

浏览器访问 <http://127.0.0.1:410/>。

### 管理商品与标注时间

Windows 用户双击 `start_local.bat`，会启动本地服务，同时打开时间标注页与商品管理页。保持启动窗口运行，关闭窗口即停止服务。

启动脚本依次使用 `PYTHON_HOME` 下的 Python、`D:\conda\env3.10\python.exe`、系统的 `py -3`。也可以直接运行：

```powershell
python serve_local.py
```

| 页面 | 本地地址 | 用途 |
| --- | --- | --- |
| 商品目录 | <http://127.0.0.1:410/> | 搜索、筛选和查看商品 |
| 时间标注 | <http://127.0.0.1:410/annotate.html> | 填写发布时间、出货时间；自动跳转到目录编辑模式 |
| 商品管理 | <http://127.0.0.1:410/product-editor.html> | 添加商品、修改属性、管理图片 |
| 更新记录 | <http://127.0.0.1:410/updates.html> | 查看采集产生的商品与图片变化 |

服务已经启动时直接访问上述地址，无需重复运行脚本。端口冲突时可用 `python serve_local.py --port 8000`，并将地址中的端口改为 `8000`；不想自动打开浏览器可加 `--no-browser`。

## 目录浏览

- 搜索商品名称、车型、年份、车手等商品文本。
- 按年份、车队、厂商、大奖赛、比例、Availability、有无样品及出货状态筛选。
- 按发布时间、出货时间、大奖赛、车队、货号、比例、Availability 和样品排序，支持升序与降序。
- 查看商品属性、描述和来源链接，浏览缩略图与大图；支持滚轮缩放、拖动及双击切换缩放。
- 自动记住搜索、筛选和排序条件，点击清除按钮可重置。

大奖赛筛选需先选择年份，无法匹配的商品归入 `OTHERS`。样品状态由图片数量及来源类型判断；出货状态由是否填写出货时间判断，与来源网站的 Availability 分开记录。

## 手动维护

### 添加或修改商品

在商品管理页左侧搜索并选择已有商品，或点击“添加商品”创建新条目。

| 字段 | 填写要求 |
| --- | --- |
| Year、Manufacturer、Scale、Product number、Availability | 必填；货号不能与其他商品重复 |
| 商品名称 | 可选；留空时按厂商、货号和年份生成 |
| 商品链接、商品描述 | 可选 |
| 其他商品详情 | 点击“＋ 添加详情项”增加；字段名不能重复或覆盖固定字段 |

图片支持 PNG、JPEG、GIF、WebP，每张不超过 15 MB，每次最多添加 30 张。多图上传还受本地服务单次请求体 64 MiB 的限制，较大图片请分批保存。点击图片可查看大图，新增与删除均在点击“保存商品”后生效。看到“已保存”后，刷新主网页查看结果。

手动数据保存在 `docs/manual-products.js`，上传图片保存在 `docs/manual-images/`。自动采集后仍保留手动属性修改、详情项删除和图片调整。手动图片优先，按 SHA-256 文件内容指纹与采集图片去重；删除采集图片后会记录其内容指纹，即使以后文件名变化，相同内容也不会重新显示。

商品管理页需要本地服务才能保存；直接打开 HTML 或访问 GitHub Pages 可浏览页面，但不能通过该页面写入本地文件。

### 标注发布时间与出货时间

在时间标注页点击商品的“添加 / 修改时间”，按 `YYYY-MM-DD` 填写。每次修改自动保存，清空表示“无”；确认显示“已保存”后再关闭。

时间统一保存在 `docs/product-times.js`，以货号为 key，包含 `published` 和 `shipped` 两个字段，自动采集不会覆盖此文件。修改后刷新目录页即可读取。

目录详情显示两个时间，缺失时显示“无”；按时间排序时，时间也显示在卡片底部。按出货时间排序时，未填写出货时间的商品始终排在末尾，再按同方向的发布时间排序。

也可直接打开 `docs/annotate.html`，在支持文件写入的 Chrome / Edge 中点击“选择时间 JS，启用自动保存”，选择 `docs/product-times.js` 并授予写入权限。普通静态 HTTP 服务只支持浏览；需要通过页面保存时，使用 `serve_local.py`。

## 采集与更新

### 运行环境

- 自动化工作流使用 Python 3.12；本地需安装兼容的 Python 3。
- 采集需要访问来源网站、图片地址及钉钉 Webhook。
- 更新记录使用 Git 中的已提交版本作比较基线，正常使用需有 Git 仓库及有效提交。

### 本地执行

先配置钉钉机器人，再依次运行三个步骤。前一步成功后再执行下一步：

```powershell
$env:DINGTALK_WEBHOOK = '钉钉机器人的完整 HTTPS Webhook 地址'
$env:DINGTALK_KEYWORD = '成绩'
python monitor.py
python catalog.py
python updates.py
```

`DINGTALK_KEYWORD` 可省略，默认值为 `成绩`，应与机器人配置的关键词一致。Webhook 通过环境变量或 GitHub Secret 提供，请勿写入项目文件。

| 步骤 | 输入与行为 | 输出 |
| --- | --- | --- |
| `monitor.py` | 检索各来源，对比上次商品列表；首次初始化或发现变化时发送钉钉通知 | `state.json` |
| `catalog.py` | 读取快照，增量采集商品详情与图片，移除下架记录及未引用的采集图片 | `docs/catalog.json`、`docs/catalog.js`、`docs/images/` |
| `updates.py` | 对比当前目录与 Git 基线，记录商品字段及图片变化 | `docs/updates.json`、`docs/updates.js` |

监控主要比较商品新增、下架、封面链接、Availability 和适用商品的 Shop 图库变化；未发生这些变化的商品通常不会重新抓取详情。钉钉通知每类最多展开 20 件商品。需要发送通知时，Webhook 缺失或发送失败会使监控步骤报错，快照不会保存为本次结果。

单个检索任务失败时，监控会保留该任务匹配的旧商品，并继续其他检索；目录中的单件详情抓取失败时保留旧记录。因此，运行完成也应检查输出中的失败提示。已有商品返回空图库时，目录保留旧图片。

Carmodel 返回 401、403 或 429 时，本轮立即停止请求该来源；临时网络错误和部分服务端错误最多尝试 3 次，每次请求超时 20 秒，间隔 2、4 秒。重试耗尽后也停止本轮 Carmodel 检索，保留对应旧商品，其他品牌继续更新。下次运行会自动重新尝试 Carmodel。此处理避免来源拒绝访问时逐车型重试耗尽 Actions 的 30 分钟限额；它不能解除来源网站对 GitHub 执行器的访问限制。

2026-10-16 实测：GitHub 执行器收到 Cloudflare 验证页（`cf-mitigated: challenge`）；完整浏览器 User-Agent、常见请求头、首页 Cookie、浏览器式 HTTP 连接和启用 JavaScript 的 Chromium 均未取得商品页。本机同一搜索返回 200 和 15 件商品。需要恢复此来源的自动采集时，应使用可访问该站的自托管执行器，或联系来源站方放行；单改请求头并未解决本次限制。

只读排查可运行 `python carmodel_probe.py`，对比原请求头、浏览器请求头和首页 Cookie；它不会保存快照或发送通知。Actions 中的 `Carmodel connectivity probe` 会在相关 PR 上运行基础诊断，也支持手动运行。手动勾选 `browser` 才安装诊断依赖并测试浏览器式连接和 Chromium；正常采集仍只需标准库。诊断任务完成表示检查执行完毕，不代表网站访问成功，需查看输出的 HTTP 状态及商品卡片数。

更新记录默认与 `HEAD` 比较，而不是与上次本地运行比较；未提交结果时重复运行可能重复记录。需要指定其他已提交基线时可运行 `python updates.py --base <提交或分支>`。

可选环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | 无 | 钉钉机器人 HTTPS Webhook，发送通知时必需 |
| `DINGTALK_KEYWORD` | `成绩` | 钉钉通知关键词 |
| `MINICHAMPS_ENABLED` | `true` | 设为 `false` 暂停 Minichamps 检索并保留旧快照 |
| `CATALOG_WORKERS` | `6` | 详情采集并发数，需为正整数 |
| `PYTHON_HOME` | 无 | Windows 启动脚本使用的 Python 所在目录 |

### 商品来源与范围

当前按配置检索 2025、2026 赛季车型，不代表来源网站的完整商品目录。关键词主要定义在 `monitor.py` 和 `carmodel.py`。

| 来源 | 2025 范围 | 2026 范围 |
| --- | --- | --- |
| Spark | C45、A525、FW47、MCL39、W16、RB21、VF-25、VCARB 02、AMR25 | VF26、MAC26、FW48、AMR26、A526、W17、R26、MCL40、VCARB03、RB22 |
| Sparkmodelshop 补充 | VCARB 02、RB21 | SF-26，用于 Looksmart 图片匹配 |
| Looksmart | SF-25 | SF-26 |
| Minichamps | 2025 Formula 1 分类 | W17、VF-26、AMR26、VCARB 03、MAC-26、A526、Audi R26、RB22、FW48、MCL40、SF-26 |
| Carmodel（Burago） | AMR25、A525、RB21、SF-25、MCL39、W16 | AMR26、A526、SF-26、RB22、MCL40、W17、VCARB-03、VF-26、FW48、MAC-26、R26 |

来源处理规则：

- Spark 与 Sparkmodelshop 按货号去重，优先保留 Spark 官网条目；Shop 补充仅收录符合条件的 2025 Spark 商品。Spark 的 2026 商品要求标题含 `2026`，并排除 `1:5` 比例。
- 2026 Looksmart 按货号匹配 Sparkmodelshop，匹配后优先采用完整 Shop 图库，封面置首并按内容去重；名称、属性、描述仍来自 Looksmart 官网。无匹配时使用官网图片，Shop 请求失败时保留上次成功的 Shop 图库。Shop 图库增图也会触发监控变化。
- Carmodel 每个车型同时检索普通商品和 Coming soon，跟随分页及 Show all，要求标题含对应年份，按 Carmodel 商品 ID 去重。保留不同货号、比例和套装；预计到货季度存入 `Expected release`。

只刷新 Burago 时，可在已有 `state.json` 的基础上运行：

```powershell
python refresh_carmodel.py
python catalog.py
python updates.py
```

`refresh_carmodel.py` 不发送钉钉通知，更新快照及 `carmodel-coverage.json`。加 `--resume` 可复用 `tmp/carmodel/` 中的缓存，缓存内容不会重新请求。

## GitHub Actions 与 Pages

将本项目目录内容作为 GitHub 仓库根目录，保留 `.github/workflows/monitor.yml`。

### 自动监控

在仓库 **Settings → Secrets and variables → Actions** 配置：

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | Secret | 机器人完整 Webhook 地址 |
| `DINGTALK_KEYWORD` | Variable，可选 | 自定义关键词，留空使用 `成绩` |

工作流名为 `Monitor Spark Models`，配置为每 10 分钟触发一次，并支持手动 **Run workflow**。单次任务上限为 30 分钟，同组任务不互相取消。

工作流先运行监控；只有 `state.json` 相比仓库发生变化时，才执行目录与记录生成。最后将变化的 `state.json` 和 `docs/` 提交并推送到仓库。因此，单件详情失败的重试也需等到目录构建步骤再次执行，或手动运行 `catalog.py`。

工作流需要 `contents: write` 权限，分支保护规则也会影响自动提交。

### 发布静态站点

1. 提交并推送完整 `docs/` 目录。
2. 在仓库 **Settings → Pages** 中选择 **Deploy from a branch**。
3. 选择包含项目的分支和 `/docs` 目录，保存后使用页面显示的站点地址。

发布手动维护结果时，要一并提交 `docs/manual-products.js`、`docs/manual-images/` 和 `docs/product-times.js`。线上目录可读取这些数据；商品写入仍通过本地服务完成。

## 文件说明

| 路径 | 用途 |
| --- | --- |
| `monitor.py` / `state.json` | 商品检索、变化通知与监控快照 |
| `catalog.py` | 详情采集、图片下载与目录生成 |
| `carmodel.py` / `refresh_carmodel.py` | Carmodel 解析与 Burago 单独刷新 |
| `carmodel-coverage.json` | Burago 单独刷新产生的各车型数量记录 |
| `updates.py` | 与 Git 基线比较并生成更新记录 |
| `serve_local.py` / `start_local.bat` | 本地浏览及商品、时间保存服务 |
| `serve_docs_410.bat` | 使用本地服务打开目录页；需配置 `PYTHON_HOME` 或指定的 Conda 路径 |
| `manual_products.py` | 手动商品合并、校验与图片指纹维护 |
| `docs/index.html` / `docs/updates.html` | 商品目录与更新记录页面 |
| `docs/annotate.html` / `docs/product-editor.html` | 时间标注入口与商品管理页 |
| `docs/catalog.json` / `docs/catalog.js` | 自动采集目录；JS 数据支持直接打开 HTML |
| `docs/updates.json` / `docs/updates.js` | 更新记录及本地浏览数据 |
| `docs/images/` | 自动采集图片 |
| `docs/manual-products.js` / `docs/manual-images/` | 手动商品数据与上传图片 |
| `docs/product-times.js` | 以货号保存的发布时间、出货时间 |
| `.github/workflows/monitor.yml` | 自动采集与提交配置 |

## 常见问题

| 问题 | 处理方法 |
| --- | --- |
| 双击启动脚本后无法运行 | 检查 Python；可直接使用 `python serve_local.py`，或设置 `PYTHON_HOME` |
| 端口已占用 | 直接访问已启动的服务，或通过 `--port` 指定其他端口 |
| 商品或时间无法保存 | 使用本地服务地址，检查启动窗口仍在运行；普通静态服务与 Pages 不提供保存接口 |
| 没有钉钉消息 | 无变化时不会发送；有变化时检查 Webhook、关键词及运行日志 |
| 商品抓取失败、图片未更新 | 检查失败日志及网站访问；详情失败保留旧数据，可再次运行 `catalog.py` |
| 提示快照来源不匹配 | 检索配置变更后先成功运行 `monitor.py`，再生成目录 |
| 本地修改后网页没变化 | 确认保存成功，刷新页面；线上还需提交并推送对应数据及图片 |
| Actions 无法提交 | 检查仓库写入权限及分支保护规则 |
