# 车模商店

本项目采集 Formula 1 模型商品信息，记录商品状态，并在钉钉发送状态提醒。静态目录展示商品资料和本地图片，可通过 GitHub Pages 发布。

项目由 Python 标准库、GitHub Actions 和静态 HTML、CSS、JavaScript 组成。Python 脚本不需要第三方依赖。

## 监控范围

程序从以下商品检索页采集列表，并沿用各站点的分页结果：

| 来源 | 查询范围 |
| --- | --- |
| Spark Model Shop | 11 个车队关键词检索，包括 2026 赛季车队商品 |
| Spark 官网 | 9 个 2025 赛季车型关键词：C45、A525、FW47、MCL39、W16、RB21、VF-25、VCARB 02、AMR25 |
| Looksmart | Ferrari SF-25 检索结果 |
| Minichamps | 10 个 2026 车型关键词：W17、VF-26、AMR26、VCARB 03、MAC-26、A526、Audi R26、RB22、FW48、MCL40 |

Ferrari 的 Spark Model Shop 结果仅收录名称包含 `SF-26` 或 `Scuderia Ferrari HP` 的商品。相同商品以商品 ID 合并。

每次采集会记录商品 ID、名称、商品链接、封面图片地址、Availability 和来源。程序以商品 ID 识别商品，并检查商品是否仍出现在检索结果中，同时比较封面图片地址与 Availability。

## 处理流程

1. `monitor.py` 请求各商品检索页，解析分页结果并汇总商品列表。
2. 程序读取 `state.json` 中上一轮的商品记录，比较商品收录状态、封面地址和 Availability。
3. 有可通知的状态时，程序向钉钉发送 Markdown 消息，并将本轮商品记录和状态写入 `state.json`。
4. GitHub Actions 将 `state.json` 加入暂存区；存在可提交内容时运行 `catalog.py`，采集相关商品详情和图片，并写入静态目录数据。
5. 随后 `updates.py` 读取 Git 提交中的目录资料，生成按时间排列的商品与图片记录。
6. 工作流将 `state.json` 和 `docs/` 提交至仓库默认分支。

首次运行会建立商品记录，并发送监控启动消息。之后，商品收录状态、封面地址或 Availability 与记录不一致时会发送提醒；没有可通知状态时不发送商品提醒。消息包含商品名称、商品链接、货号、比例及对应状态。每个提醒类别最多列出 20 件商品。

## 静态商品目录

`docs/index.html` 展示 `docs/catalog.json` 中的商品。商品卡片包含名称、图片、比例、年份、货号和 Availability；“商品详情”区域可查看其余商品属性及描述。商品名称链接指向来源站点。

目录提供以下搜索、筛选和排序项：

- 关键词：搜索商品记录中的文字，例如商品名称、车型、年份或车手。
- 年份、车队、厂商、比例、分类和 Availability。
- 大奖赛：先选择年份，再从该年度赛历中选择名称；选项可显示比赛日期。无法归入已识别大奖赛的商品列为 `OTHERS`。
- 样品：商品图片超过一张时归类为“有样品”。
- 排序：默认顺序、大奖赛、车队、货号、比例、Availability 及样品数量；箭头控制升序或降序。
- 清除筛选：恢复所有搜索和筛选条件。

分类规则将比例 `1/5` 归为头盔，其他比例归为车模。比例筛选按模型尺寸排列，例如 `1/64`、`1/43`、`1/18`、`1/12`、`1/5`。页面记住浏览器本地存储中的搜索、筛选和排序条件。

点击商品图片可打开图片浏览层。浏览层支持商品图片切换、商品切换、缩略图选择、滚轮缩放和拖动；双击图片可在 1 倍和 2 倍缩放间切换。键盘左右方向键切换图片，`Esc` 关闭浏览层。“定位商品”关闭浏览层并滚动到对应商品卡片。移动设备可在主图上左右滑动切换图片。

商品图片由 `catalog.py` 保存到 `docs/images/`，页面引用仓库中的本地副本。商品目录顶部显示数据生成时间，右上角入口打开按时间排列的商品及图片记录页。

## 文件与数据

| 路径 | 用途 |
| --- | --- |
| `monitor.py` | 请求商品检索页、汇总列表、比较商品状态并发送钉钉消息 |
| `catalog.py` | 采集商品详情、下载图片、整理目录数据并清理未引用图片 |
| `updates.py` | 对照 Git 提交中的目录，生成商品和图片记录 |
| `state.json` | 商品列表快照、数据来源地址、采集时间及状态记录 |
| `docs/index.html` | 商品目录页面及交互逻辑 |
| `docs/catalog.json` | 静态目录使用的商品数据 |
| `docs/catalog.js` | 将商品数据提供给页面脚本，也可用于本地文件预览 |
| `docs/images/` | 商品图片的本地副本 |
| `docs/updates.html` | 商品与图片记录页面 |
| `docs/updates.json` | 记录页使用的数据 |
| `docs/updates.js` | 记录数据的脚本格式，供本地文件预览使用 |
| `.github/workflows/monitor.yml` | GitHub Actions 定时任务与手动任务配置 |
| `serve_docs_410.bat` | Windows 本地预览启动脚本，监听 `127.0.0.1:410` |

`catalog.json` 顶层包含 `generated_at` 和 `products`。每件商品记录含有 `id`、`name`、`url`、`images`、`properties`、`description`、`brand`、价格、重量、尺寸及 Availability 等字段；具体字段取决于商品来源。

## 运行环境

- Python 3.12 或兼容版本。
- Git，用于运行 `updates.py` 和 GitHub Actions 自动提交。
- 网络连接，用于访问商品来源站点、下载商品图片及调用钉钉 Webhook。

Python 脚本仅使用标准库。静态页面不需要 Node.js、数据库或服务器端运行环境。

## GitHub Actions 配置

将 `sparkmodel-monitor` 目录的全部内容放到 GitHub 仓库根目录，`.github/workflows/monitor.yml` 也需一并提交。

在仓库 `Settings` → `Secrets and variables` → `Actions` 中设置：

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `DINGTALK_WEBHOOK` | Secret | 钉钉自定义机器人的完整 HTTPS Webhook 地址 |
| `DINGTALK_KEYWORD` | Variable，可选 | 机器人要求的自定义关键词；未设置时程序使用 `成绩` |

工作流名称为 `Monitor Spark Model Shop`，可从 `Actions` 页面手动运行。定时表达式 `*/10 * * * *` 表示每小时的第 0、10、20、30、40、50 分钟触发。GitHub 定时任务的实际开始时间可能晚于计划时间。单次任务最长运行 30 分钟，同一工作流任务按队列顺序执行，不会相互取消。

工作流需要仓库内容写入权限，配置为 `contents: write`。若默认分支的保护规则要求审查或限制写入，GitHub Actions 需要符合对应规则才能推送提交。

## GitHub Pages 发布

在仓库 `Settings` → `Pages` 中配置：

1. Source 选择 `Deploy from a branch`。
2. Branch 选择包含项目文件的默认分支。
3. Folder 选择 `/docs`。
4. 保存后，使用 GitHub Pages 页面提供的站点地址浏览目录。

工作流将目录文件提交至该分支后，GitHub Pages 使用 `/docs` 中的 HTML、JSON、JavaScript 和图片提供静态页面。

## 本地运行与预览

在 PowerShell 中进入 `sparkmodel-monitor` 目录，设置钉钉 Webhook 后运行监控：

```powershell
$env:DINGTALK_WEBHOOK='钉钉机器人的完整 HTTPS 地址'
$env:DINGTALK_KEYWORD='机器人设置的关键词'
python monitor.py
```

`DINGTALK_KEYWORD` 为可选环境变量。如果机器人没有配置自定义关键词，可以省略。

`catalog.py` 读取 `state.json` 中本轮标记的商品 ID，并据此采集相关商品详情和图片。目录缺少某件已收录商品时，脚本也会采集该商品。`updates.py` 需要 Git 仓库和有效的 `HEAD` 提交，用于读取仓库提交中的目录记录。

使用以下命令在本机启动静态页面：

```powershell
python -m http.server 8000 --directory docs
```

浏览器访问 `http://localhost:8000/`。Windows 用户也可运行 `serve_docs_410.bat`，再访问 `http://127.0.0.1:410/`。HTTP 服务用于提供页面和 JSON 文件；直接打开 HTML 文件时，部分浏览器会限制 JSON 读取。

## 配置与安全

商品关键词和来源检索地址定义在 `monitor.py` 的常量中。`catalog.py` 会校验 `state.json` 中保存的来源地址是否对应脚本配置；两者不符时会停止目录处理，避免混用不同检索配置的数据。

钉钉 Webhook 通过 `DINGTALK_WEBHOOK` 环境变量或 GitHub Actions Secret 提供。程序要求其使用 HTTPS，主机名属于 `dingtalk.com`。不要将 Webhook 或访问凭证写入代码、README、`state.json` 或 Git 提交。

## 常见问题

- **没有收到钉钉消息**：检查 `DINGTALK_WEBHOOK` 是否为有效的 HTTPS 钉钉地址，以及 GitHub Secret 是否正确设置；机器人启用关键词校验时，检查 `DINGTALK_KEYWORD` 是否与机器人设置一致。
- **Actions 无法提交**：检查工作流的仓库内容写入权限和默认分支保护规则。
- **页面没有商品或图片**：检查 `docs/catalog.json`、`docs/catalog.js` 和 `docs/images/` 是否存在，并通过本地 HTTP 服务或已发布的 Pages 地址访问页面。
- **目录脚本提示来源地址不匹配**：检查 `monitor.py` 中的检索配置和 `state.json` 中保存的 `sources` 是否对应。`state.json` 是监控基线文件，手动移除该文件或覆盖其中内容会影响后续的状态比较。
- **记录页图片无法显示**：记录页读取仓库中的图片副本；已不在 `docs/images/` 中的旧图片不再有可用文件，记录数据仍保留对应图片数量信息。
