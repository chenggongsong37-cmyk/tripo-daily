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

公开 RSS/Atom/API 在 `config/sources.json`，当前包含 OpenAI、Google DeepMind、Hugging Face、NVIDIA、Google AI、Microsoft Research、arXiv，以及 Google News 的英文/中文公开摘要检索。Google News 是媒体聚合，不代表原始媒体核验；报告会标明来源类型。竞品 Meshy、Rodin/Hyper3D、Deemos/影眸科技目前通过公开检索词发现，若其官网提供稳定 RSS/API，可直接加入配置。程序不绕过登录、付费墙、验证码或 robots；没有 RSS/API 的站点不能把网页结构当 API。抓取失败会记录并以非零状态退出，同时保留覆盖不完整提示。关键词和竞品可在 `tripo_daily/core.py` 配置；API 密钥只放 `.env`。运行测试：先执行 `pip install -e '.[dev]'`，再运行 `pytest`。

常见故障：网络或证书错误先运行 `sources check`；来源暂时不可用时查看报告“采集说明”；没有模型密钥属于正常的待审核模式。当前示例来源是否可访问取决于网络和对方 RSS 实际状态，本项目没有声称已验证实时新闻。
