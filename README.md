# daily-pipeline

定时数据收集管道：GitHub Actions 负责"脏活累活"（抓数据），Muse 负责"动脑"（摘要、评分、判断）。

## 为什么这样拆

- Actions 的算力免费（private repo 每月 2000 分钟），爬虫/API 请求不消耗 Muse 的周额度。
- 需要登录态、设备、资金凭证、强反爬站点的任务留在 Muse 侧。
- 两边用 repo 里的 JSON 文件交接：Actions 写，Muse 读。

## 管道一览

| 管道 | Actions 做什么 | Muse 做什么 | 节奏 |
|---|---|---|---|
| `freelance-leads` | 每周一 06:37 PT 抓 HN + 融资新闻，写入 `freelance-leads/data/latest.json` | 读 JSON，与 Reddit / X / 社交 / 平台四个源合并，去重打分，推送 | 每周一 08:00 PT |

## 加新管道

1. 在 repo 根建 `<name>/` 目录：`scripts/` 放采集脚本，`data/` 放产出。
2. 在 `.github/workflows/` 加 `<name>-collect.yml`（参考现有文件：schedule + workflow_dispatch，`contents: write` 权限，抓完 commit 回 `data/`）。
3. 定时注意和 GitHub scheduler 错峰：分钟用非整点（如 37 分）。

## 注意事项

- 机房 IP 反爬：LinkedIn、Redfin/Zillow、小红书官方站不要碰，只用公开 API / RSS / 允许爬的聚合页。
- 不要在 repo 里放任何密钥、登录凭证、私人数据。需要 key 的源走 Secrets，且先和用户确认。
- 60 天无提交的 repo 会被 GitHub 暂停 workflow——本 repo 每周都有提交，不受影响。
