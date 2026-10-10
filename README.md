# Tripo AI 舆情与行业日报

这是一个 Python 3.11+ 的本地命令行工具：读取公开 RSS，按北京时间每天 10:30 的 24 小时窗口筛选新闻，写入 SQLite，并生成中文 Markdown 和 HTML。模型接口是可选的；没有密钥时会保留“待审核”摘要，不会凭空补新闻。

## 安装和首次演示

在项目目录运行：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m tripo_daily.cli run --date 2026-10-08 --sample
```

样本会明确标为“样本”且使用 example.invalid，不会混入真实日报。报告在 `reports/2026-10-08.md` 和同名 HTML。查看候选而不写报告：`python -m tripo_daily.cli preview --sample`。真实采集：`python -m tripo_daily.cli run`；补跑：`... backfill --date 2026-10-01`；检查来源：`... sources check`。

## 网页版

启动本地网页：

```bash
source .venv/bin/activate
python -m tripo_daily.web
```

然后打开 http://127.0.0.1:8765。页面显示最新 HTML 日报，点击“刷新日报”会实际重新采集并生成当天报告。默认只监听本机，按 Ctrl+C 停止。

## 免费公网部署

项目已包含 `Dockerfile` 和 `render.yaml`，可部署到 Render 的 Free Web Service：将项目放到 GitHub 后，在 Render 选择 New → Web Service，连接仓库并选择 Docker，计划选择 Free，创建服务即可。平台会自动注入 `PORT`，应用监听 `0.0.0.0`。免费实例可能休眠，首次打开或刷新需要等待唤醒；SQLite 和本地报告文件适合演示与轻量使用，重启后不保证持久保存。不要把模型密钥提交到仓库，在平台环境变量中填写。

项目也包含 `vercel.json` 和 `api/index.py`，用于 Vercel Python Serverless 部署。Vercel 部署适合展示和轻量刷新；免费函数实例不保证本地 SQLite 持久化，长期使用应换成外部数据库或对象存储。

## 定时运行

macOS 用 launchd 的 `StartCalendarInterval` 设置 `Hour=10, Minute=30`，ProgramArguments 指向 `.venv/bin/tripo-daily run`，StandardOut/Err 写入项目日志；Linux 可用 systemd service + timer（`OnCalendar=*-*-* 10:30:00 Asia/Shanghai`，`Persistent=true`）。电脑关机时不会运行，需部署到持续运行主机。默认不发送邮件、企业微信或飞书。

## 配置来源和限制

公开 RSS/Atom/API 在 `config/sources.json`，当前包含 28 个已实际检查可访问的来源：OpenAI、Google DeepMind、Hugging Face、NVIDIA、Google AI、Microsoft Research、AWS、Unity、腾讯混元 GitHub Releases、arXiv，爱范儿、量子位、极客公园、VR陀螺、人民网中英文频道、Global Times 官方 RSS，以及 Google News 的中英文行业、监管、中美 AI 与芯片政策主题检索。Google News 是媒体聚合，不代表原始媒体核验；报告会标明来源类型。当前竞品包括 Meshy、影眸科技/Deemos（平台 Hyper3D，产品 Rodin）、腾讯混元/Hunyuan3D、阿里 Happy Horse，主要通过公开检索词发现；若其官网提供稳定 RSS/API，可直接加入配置。程序不绕过登录、付费墙、验证码或 robots；没有 RSS/API 的站点不能把网页结构当 API。抓取失败会记录并以非零状态退出，同时保留覆盖不完整提示。关键词和竞品可在 `tripo_daily/core.py` 配置；API 密钥只放 `.env`。运行测试：先执行 `pip install -e '.[dev]'`，再运行 `pytest`。

常见故障：网络或证书错误先运行 `sources check`；来源暂时不可用时查看报告“采集说明”；没有模型密钥属于正常的待审核模式。当前示例来源是否可访问取决于网络和对方 RSS 实际状态，本项目没有声称已验证实时新闻。

## Supabase 历史存储与飞书每日推送

1. 在 Supabase 新建免费项目，打开 SQL Editor，复制执行 `supabase/schema.sql`。
2. 在 Project Settings → API 获取 Project URL 和 `service_role` key。`service_role` 只能配置在 Vercel 服务端，禁止放入网页或提交 Git。
3. 在 Vercel 项目 Settings → Environment Variables 添加 `SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`。
4. 在飞书群添加自定义机器人，把 Webhook 和签名密钥分别填入 Vercel 的 `FEISHU_WEBHOOK_URL`、`FEISHU_SIGNING_SECRET`。
5. 在 Vercel 增加随机长字符串 `CRON_SECRET`，然后重新部署。

`vercel.json` 已配置 `30 2 * * *`，即每天 UTC 02:30、北京时间 10:30 调用 `/api/cron/daily`。定时任务会生成日报、按日期写入 Supabase，并在配置飞书后推送群卡片。Supabase 未配置时网页仍可运行，但不会持久保存历史；飞书未配置时只保存日报，不发送消息。

Vercel Hobby 的定时任务可能在设定小时内延迟执行，并非秒级准点。若日报已生成但飞书发送失败，可使用带 `Authorization: Bearer $CRON_SECRET` 的请求调用 `/api/cron/feishu` 单独重试；该接口只发送 Supabase 中当天的日报，不会重新采集，也不会发送旧日报。
