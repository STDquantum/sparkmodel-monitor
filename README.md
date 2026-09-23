# Spark Model Shop Formula 1 变化监控

定时抓取 Spark Model Shop 的 11 个 2026 车队搜索结果、Spark 官网的 9 个 2025 车型查询，以及 Looksmart 官网的 Ferrari SF-25 搜索结果，监控商品新增、下架、封面和 Availability 变化。发现变化后发送钉钉通知，并重新生成可部署到 GitHub Pages 的静态商品目录。2026 Ferrari 搜索结果仅保留标题含 `SF-26` 或 `Scuderia Ferrari HP` 的商品。

项目仅使用 Python 标准库，不需要安装额外依赖。

## 功能

- 从第 1 页抓取到最后一页，并校验抓取数量是否完整。
- 使用 `state.json` 保存商品快照，比较新增、封面变化、Availability 变化和下架；钉钉消息标出具体字段变化。
- 首次建立基线时发送启动消息；之后只在发生变化时通知。
- 变化通知列出商品名称、货号和比例。
- 只有监控结果变化时，才运行详情爬虫；只抓取新增和封面变化的商品详情。
- 下载发生变化商品的全部图片到 `docs/images/`，并删除下架商品和已替换图片的本地文件；网页不依赖远程图片。
- 每次目录变化后生成更新报告，按图片内容区分真正新增、替换与仅换位置；新增或替换的图片排在该商品图集最前面。报告入口位于主页右上角。
- 更新报告沿用商品页的深色卡片样式，点击报告图片可放大、切图和缩放。
- GitHub Actions 每小时第 17 分钟运行，也支持手动运行。

静态商品页支持：

- 关键词、年份、车队、大奖赛、比例、分类和样品筛选；图片多于一张即“有样品”。大奖赛先选年份，再按该年度官方赛历选择大奖赛名称，并显示每站最后一天；`Preseason` 在最前、`OTHERS` 在最后；无法识别大奖赛的商品归为 `OTHERS`；`1/5` 归为头盔，其余比例归为车模。
- 比例按模型尺寸从小到大排列：`1/64 → 1/43 → 1/18 → 1/12 → 1/5`。
- 商品卡片展示 Scale、Year、Product number 和 Availability，其余参数可悬浮查看。
- 大图内显示比例、年份和货号。
- 桌面端内侧箭头循环当前商品图片，外侧双箭头切换不同商品；移动端左右滑动主图切图，仅保留两侧商品切换按钮。
- 滚轮缩放最高 8 倍，放大后可拖动；双击在 1 倍和 2 倍间切换。
- “定位商品”可关闭大图、返回对应卡片并短暂高亮。

## 文件说明

- `monitor.py`：抓取商品列表、比较快照并发送钉钉通知。
- `catalog.py`：增量抓取变更商品详情、同步本地图片并生成 `docs/catalog.json`。
- `state.json`：最近一次商品列表快照及本轮变更商品 ID。
- `docs/index.html`：GitHub Pages 静态展示页面。
- `docs/catalog.json`：静态页面使用的商品数据。
- `docs/images/`：下载到本地的商品图片。
- `updates.py`：比较本轮目录与上次提交，生成商品及图片变化记录。
- `docs/updates.json`、`docs/updates.html`：更新历史数据与报告页面。报告直接引用 `docs/images/`，每次更新用内容哈希检查历史图片；仅移除已变化或已删除图片的旧引用，保留原更新数量。
- `.github/workflows/monitor.yml`：定时监控、建站和自动提交工作流。

## GitHub 部署

1. 新建 GitHub 仓库，把本目录全部内容上传到仓库根目录，包括 `.github`。
2. 打开仓库 `Settings` → `Secrets and variables` → `Actions`。
3. 在 `Secrets` 中新增 `DINGTALK_WEBHOOK`，值为钉钉机器人的完整 HTTPS 地址。
4. 如果机器人启用了“自定义关键词”，在 `Variables` 中新增 `DINGTALK_KEYWORD`，值必须与机器人设置完全一致；未设置时默认使用 `成绩`。
5. 打开 `Actions` → `Monitor Spark Model Shop` → `Run workflow`，手动运行一次以检查配置。

不要把钉钉 Webhook 或 access token 直接写入代码、README 或提交记录。

工作流会执行以下步骤：

1. 抓取商品列表并发送必要的钉钉通知。
2. 检查 `state.json` 是否变化；无变化时跳过详情爬虫。
3. 有变化时运行 `catalog.py` 和 `updates.py`，更新商品目录、图片和更新报告，并删除已下架商品的目录图片。
4. 自动提交并推送 `state.json` 和 `docs/`。

定时表达式是 `17 * * * *`。GitHub 定时任务可能延迟几分钟，并非严格在每小时第 17 分钟启动。

如果默认分支启用了保护规则，需要允许 GitHub Actions 写入仓库，否则自动提交会失败。

## GitHub Pages

打开仓库 `Settings` → `Pages`：

1. Source 选择 `Deploy from a branch`。
2. Branch 选择默认分支。
3. Folder 选择 `/docs`。
4. 保存后等待 GitHub Pages 完成发布。

## 本地运行

要求 Python 3.12 或兼容版本。

PowerShell：

```powershell
$env:DINGTALK_WEBHOOK='你的钉钉机器人完整地址'
$env:DINGTALK_KEYWORD='钉钉机器人配置的关键词'

python monitor.py
```

手动同步最近一轮变更的详情和图片：

```powershell
python catalog.py
```

本地预览静态页面：

```powershell
python -m http.server 8000 --directory docs
```

然后访问 `http://localhost:8000/`。

`catalog.py` 会依据 `state.json` 中本轮变更的商品 ID，重新请求新增和封面变化商品的详情并同步图片；目录中缺失的商品也会自动补齐。正常的 GitHub Actions 工作流只会在列表监控发现变化后运行它。
