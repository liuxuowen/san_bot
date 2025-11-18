# San Bot - 微信服务号文件分析助手

San Bot 现在以微信公众号（服务号）作为默认对话入口，普通微信用户可以直接向服务号发送分析指令与文件，机器人会在后台完成对比分析并通过客服消息返回结论；企业微信应用仍可选用，方便旧流程平滑迁移或双通道部署。

## 功能亮点

- ✅ 微信服务号原生接入，支持文本指令、文件/图片上传与客服消息回推
- ✅ 企业微信应用兼容模式，可同时挂载两个入口
- ✅ 文件对比、同盟战功 CSV 深度分析与分组图表输出
- ✅ RESTful API (`/api/analyze`) 便于集成到其他系统
- ✅ 统一的会话管理与后台异步分析，避免回调超时

## 架构概览

```
┌───────────────┐      ┌──────────────────────┐
│  微信服务号    │────▶│ /sanbot/service/callback │
└───────────────┘      │  (Flask Blueprint)   │
                        └────────────┬─────────┘
                                      │
┌───────────────┐      ┌──────────────▼─────────────┐
│ 企业微信 (可选) │────▶│ /wechat/work/callback      │
└───────────────┘      └──────────────┬─────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │ SessionStore + Analyzer │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │ FileAnalyzer / 图像渲染 │
                         └─────────────────────────┘
```

- `sanbot/app_factory.py` 负责装配 Flask、路由与依赖
- `sanbot/session_store.py` 管理每个用户的指令与文件
- `sanbot/services/analysis.py` 在后台线程中运行长耗时分析
- `sanbot/wechat/service_account.py` / `wechat_api.py` 提供统一的消息发送接口

## 环境准备

1. 克隆并进入仓库

```bash
git clone https://github.com/liuxuowen/san_bot.git
cd san_bot
```

2. 安装依赖（建议使用虚拟环境）

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. 配置环境变量

```bash
cp .env.example .env
```

`.env` 需要至少配置以下字段：

```
# 微信服务号（推荐）
FUWUHAO_APP_ID=wx...
FUWUHAO_APP_SECRET=...
FUWUHAO_TOKEN=与微信后台保持一致
FUWUHAO_ENCODING_AES_KEY=可留空（当前仅支持明文模式）

# （可选）企业微信
WECHAT_CORP_ID=
WECHAT_CORP_SECRET=
WECHAT_AGENT_ID=
WECHAT_TOKEN=
WECHAT_ENCODING_AES_KEY=

# 通用
SECRET_KEY=your-secret
FLASK_ENV=development
PORT=7000
HIGH_DELTA_THRESHOLD=5000
```

> ⚠️ 当前版本仅支持 **明文模式** 的微信服务号回调；若后台使用安全模式，请先切换到明文。

## 运行与调试

### 使用启动脚本

```bash
./start.sh
```

脚本会自动创建虚拟环境、安装依赖并运行 `python app.py`。

### 手动启动

```bash
FLASK_ENV=development python app.py
```

服务默认监听 `http://0.0.0.0:7000`，可在 `.env` 中修改 `HOST/PORT`。

### API 自测

```bash
curl -X POST http://localhost:7000/api/analyze \
  -F "file1=@/path/a.csv" \
  -F "file2=@/path/b.csv" \
  -F "instruction=对比两个报表"
```

## 微信服务号接入指南

1. 登录 [mp.weixin.qq.com](https://mp.weixin.qq.com/)
2. 进入「开发」→「基本配置」→「服务器配置」
3. 启用服务器配置，设置：
   - URL: `https://<你的域名>/sanbot/service/callback`
   - Token: 使用 `.env` 中的 `FUWUHAO_TOKEN`
   - 消息加解密方式: 明文模式
4. 在「接口权限」中确认客服消息能力已开通
5. 交互流程：
   - 用户发送文本 → 机器人记录指令并提示上传
   - 用户上传两个文件/图片 → 后台分析 → 通过客服消息回传结论或图片

### 服务号指令说明

- 当前仅支持两条分析指令，均需先发送文本指令再上传两份 **CSV** 文件：
  - `战功差`：比对两份同盟统计 CSV，统计所有成员的「战功总量」差值，并按照分组分片生成榜单及图片。
  - `势力值`：比对两份同盟统计 CSV，统计所有成员的「势力值」差值，输出方式同上。
- 任何其他指令都会得到提示 `暂不支持指令，目前仅支持【战功差】以及【势力值】`，不会记录到会话中。
- 若未先发送有效指令即上传文件，系统会引导用户先选择指令再重新上传，以保证分析链路明确。

## 企业微信兼容模式（可选）

- 登录企业微信管理后台 → 应用管理 → 创建应用
- 在应用的「接收消息」中配置 URL：`https://<域名>/wechat/work/callback`
- 保持 `.env` 中的 `WECHAT_*` 参数与后台一致
- 两个通道共用同一套会话与分析逻辑

## 项目结构

```
.
├── app.py                     # 入口，仅负责加载 create_app
├── sanbot/
│   ├── __init__.py            # 导出 create_app
│   ├── app_factory.py         # Flask 工厂与依赖装配
│   ├── routers/
│   │   ├── api.py             # /api/analyze
│   │   ├── service_account.py # /sanbot/service/callback
│   │   └── work.py            # /wechat/work/callback
│   ├── services/
│   │   └── analysis.py        # 异步分析任务
│   ├── session_store.py       # 会话管理
│   └── wechat/
│       └── service_account.py # 服务号 API 封装
├── file_analyzer.py           # 核心分析逻辑（兼容旧引用）
├── wechat_api.py              # 企业微信 API 封装
├── resources/                 # 模板 / 头图 / 成语 JSON
├── requirements.txt
├── README.md
└── ...
```

## 测试与演示

- CLI 演示：`python test_demo.py`
- 语法/依赖检测示例：

```bash
python -m compileall sanbot app.py
```

## 部署建议

1. 使用 `deploy.sh` 将代码同步到服务器并创建虚拟环境
2. 生产环境建议使用 HTTPS，`HOST` 设为 `0.0.0.0`
3. 若使用多进程（Gunicorn 等），请将 `SessionStore` 替换为 Redis/DB 实现
4. 企业微信与服务号可同时配置，必要时在反向代理层拆分路径

## 常见问题

| 问题 | 解决方案 |
| --- | --- |
| 服务号校验失败 | 确保 Token 一致、消息模式为明文，并检查公网可达性 |
| 上传后无响应 | 查看服务器日志，确认分析线程是否异常；必要时增大 `HIGH_DELTA_THRESHOLD` 以减少图表渲染量 |
| 需要更大文件 | 修改 `.env` 或 `config.py` 中的 `MAX_CONTENT_LENGTH`，并确保反向代理允许更大请求 |

如需新特性或发现问题，欢迎提交 Issue / PR。
