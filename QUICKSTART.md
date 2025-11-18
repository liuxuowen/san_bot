# 快速开始（服务号 + 企业微信）

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置环境变量

```bash
cp .env.example .env
```

需要重点填写：

- `FUWUHAO_APP_ID` / `FUWUHAO_APP_SECRET` / `FUWUHAO_TOKEN`（服务号）
- `WECHAT_*`（如需企业微信兼容）
- `PORT`、`HOST`、`HIGH_DELTA_THRESHOLD` 等通用项

## 3. 运行应用

### 启动脚本（推荐）

```bash
./start.sh
```

### 手动方式

```bash
FLASK_ENV=development python app.py
```

服务默认监听 `http://0.0.0.0:7000`。

## 4. 接入微信服务号

1. 登录 [mp.weixin.qq.com](https://mp.weixin.qq.com/)
2. 在「开发」→「基本配置」中启用服务器配置
3. 设置回调 URL：`https://<域名>/sanbot/service/callback`
4. Token 与 `.env` 中 `FUWUHAO_TOKEN` 保持一致
5. 消息加解密方式选择 **明文模式**
6. 提交后即可通过手机微信与服务号交互

## 5. （可选）接入企业微信

1. 在企业微信管理后台创建自建应用
2. 在“接收消息”中设置 URL：`https://<域名>/wechat/work/callback`
3. 将企业 ID、Secret、AgentId、Token、EncodingAESKey 填入 `.env`

## 6. 验证功能

### API 调用

```bash
curl -X POST http://localhost:7000/api/analyze \
  -F "file1=@tests/a.csv" \
  -F "file2=@tests/b.csv" \
  -F "instruction=对比两个报表"
```

### 本地演示

```bash
python test_demo.py
```

## 7. 常见问题

| 问题 | 解决思路 |
| --- | --- |
| 服务号校验失败 | 确认 Token、明文模式以及公网可达性 |
| 上传后无响应 | 查看日志，确认分析线程是否抛错；必要时提高超时或减小文件大小 |
| 图片发送失败 | 检查 `resources/header2.jpg` 是否存在，以及服务号是否具备素材上传权限 |

完成上述步骤后，普通微信用户即可通过服务号发送指令与文件，实现和原企微机器人的同样体验。

