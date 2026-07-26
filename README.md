# Spark Model Shop Formula 1 变化监控

每小时从第 1 页抓取到最后一页，监控 [Spark Model Shop Formula 1](https://www.sparkmodelshop.com/de/en/models/formula/formula-1/?properties=881036a7528b682be67aa6e2c171e1de&p=1&order=release-date-desc) 商品。发现新增、封面变化或下架后，通过钉钉自定义机器人发送消息；快照由 GitHub Actions 自动提交到 `state.json`。

## 部署

1. 新建一个 GitHub 仓库，把本目录中的全部内容上传到仓库根目录（要保留 `.github` 隐藏目录）。
2. 在仓库 `Settings` → `Secrets and variables` → `Actions` → `Secrets` 中新增：
   - 名称：`DINGTALK_WEBHOOK`
   - 值：完整机器人地址，如 `https://oapi.dingtalk.com/robot/send?access_token=新token`
3. 如果机器人启用了“自定义关键词”，在同一页面的 `Variables` 中新增 `DINGTALK_KEYWORD`，值必须与钉钉设置的关键词完全一致。未设置时消息默认包含 `成绩`。
4. 打开 `Actions` → `Monitor Spark Model Shop` → `Run workflow` 手动运行一次。第一次会建立基线并发送“监控已启动”；以后仅在有变化时通知。

定时表达式为每小时第 17 分钟执行。GitHub 的定时任务可能有几分钟延迟，并非严格整点。

## GitHub Pages

列表变化后，工作流会抓取每个商品详情及全部原图，生成并提交 `docs/index.html`、`docs/catalog.json` 与 `docs/images/`。在仓库 `Settings` → `Pages` 中选择 `Deploy from a branch`，设置为默认分支的 `/docs` 目录即可发布静态网页。首次手动运行监控也会生成该目录。

若需本地重新生成静态目录，运行 `python catalog.py`。该脚本会覆盖同名图片并更新 `catalog.json`。

## 本地检查

PowerShell：

```powershell
$env:DINGTALK_WEBHOOK='你的新机器人完整地址'
$env:DINGTALK_KEYWORD='你在钉钉配置的关键词'
python -m unittest -v
python monitor.py
```

如果默认分支启用了禁止机器人直接推送的保护规则，需要允许 GitHub Actions 写入，或者取消对 `state.json` 的分支保护。
