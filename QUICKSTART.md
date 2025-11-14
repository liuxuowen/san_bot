# 快速开始指南

## 第一步：安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt
```

## 第二步：配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的企业微信配置
vim .env
```

需要配置的参数：
- `WECHAT_CORP_ID`: 企业ID（在企业微信管理后台"我的企业"页面获取）
- `WECHAT_CORP_SECRET`: 应用Secret（在应用详情页获取）
- `WECHAT_AGENT_ID`: 应用AgentId（在应用详情页获取）
- `WECHAT_TOKEN`: Token（在应用接收消息配置页面设置）
- `WECHAT_ENCODING_AES_KEY`: EncodingAESKey（在应用接收消息配置页面设置）

## 第三步：运行应用

### 方式1：使用启动脚本（推荐）

```bash
./start.sh
```

### 方式2：直接运行

```bash
python app.py
```

### 方式3：使用 Docker

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 第四步：测试功能

### 测试 API

```bash
# 准备两个测试文件
echo "Hello World" > file1.txt
echo "Hello Python" > file2.txt

# 调用分析接口
curl -X POST http://localhost:5000/api/analyze \
  -F "file1=@file1.txt" \
  -F "file2=@file2.txt" \
  -F "instruction=对比这两个文件"
```

### 运行演示程序

```bash
python test_demo.py
```

## 第五步：配置企业微信

1. 登录[企业微信管理后台](https://work.weixin.qq.com/)
2. 进入"应用管理" → "应用" → "创建应用"
3. 在应用详情页，配置"接收消息"：
   - URL: `http://你的域名/wechat/callback`
   - Token: 填入 .env 文件中的 WECHAT_TOKEN
   - EncodingAESKey: 填入 .env 文件中的 WECHAT_ENCODING_AES_KEY
4. 保存配置

## 使用机器人

1. 在企业微信中打开你创建的应用
2. 发送文本消息，描述分析需求（例如："对比两个配置文件"）
3. 上传第一个文件
4. 上传第二个文件
5. 等待机器人返回分析报告

## 常见问题

### Q: 如何查看日志？
A: 应用日志会输出到控制台，可以重定向到文件：
```bash
python app.py > app.log 2>&1
```

### Q: 如何修改端口？
A: 在 .env 文件中设置 `PORT=你的端口号`

### Q: 支持哪些文件格式？
A: txt, csv, json, xlsx, xls, pdf, doc, docx

### Q: 文件大小限制是多少？
A: 默认 16MB，可在 config.py 中修改 `MAX_CONTENT_LENGTH`

### Q: 如何部署到生产环境？
A: 推荐使用 Docker 或 Gunicorn：
```bash
# 使用 Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# 或使用 Docker
docker-compose up -d
```

## 获取帮助

- 查看 README.md 了解详细文档
- 运行 `python test_demo.py` 查看功能演示
- 提交 Issue 报告问题

## 升级维护

```bash
# 更新代码
git pull origin main

# 更新依赖
pip install -r requirements.txt --upgrade

# 重启服务
docker-compose restart  # 如果使用 Docker
# 或
./start.sh  # 如果使用启动脚本
```
