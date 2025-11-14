# San Bot - 企业微信文件分析机器人

基于企业微信的文件分析机器人，使用 Python Flask 框架开发。机器人可以接收2个文件和1个指令，根据指令进行文件对比，并输出结论报告。

## 功能特性

- ✅ 企业微信机器人集成
- ✅ 支持多种文件格式 (txt, csv, json, xlsx, xls, pdf, doc, docx)
- ✅ 智能文件对比分析
- ✅ 自动生成详细的对比报告
- ✅ 支持自定义分析指令
- ✅ RESTful API 接口

## 技术栈

- Python 3.8+
- Flask 3.0.0
- Pandas (Excel文件处理)
- Requests (企业微信API调用)

## 快速开始

### 1. 环境要求

- Python 3.8 或更高版本
- pip 包管理器

### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/liuxuowen/san_bot.git
cd san_bot

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖包
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 文件为 `.env`，并填入你的企业微信配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下信息：

```ini
# Flask 配置
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
DEBUG=True
HOST=0.0.0.0
PORT=5000

# 企业微信配置
WECHAT_CORP_ID=your-corp-id           # 企业ID
WECHAT_CORP_SECRET=your-corp-secret   # 应用Secret
WECHAT_AGENT_ID=your-agent-id         # 应用AgentId
WECHAT_TOKEN=your-token               # Token（用于验证）
WECHAT_ENCODING_AES_KEY=your-aes-key  # EncodingAESKey
```

### 4. 运行应用

```bash
python app.py
```

服务将在 `http://0.0.0.0:5000` 启动。

## 使用指南

### 企业微信机器人使用流程

1. **发送指令**: 在企业微信中向机器人发送文本消息，描述分析需求
   - 例如："对比两个文件的差异"
   - 例如："分析配置文件的变更"

2. **上传第一个文件**: 发送第一个需要对比的文件

3. **上传第二个文件**: 发送第二个需要对比的文件

4. **获取报告**: 机器人自动分析并返回详细的对比报告

### API 接口使用

#### POST /api/analyze

用于直接通过 API 进行文件分析。

**请求参数:**
- `file1`: 第一个文件（multipart/form-data）
- `file2`: 第二个文件（multipart/form-data）
- `instruction`: 分析指令（可选，默认："对比两个文件的差异"）

**示例:**

```bash
curl -X POST http://localhost:5000/api/analyze \
  -F "file1=@file1.txt" \
  -F "file2=@file2.txt" \
  -F "instruction=对比两个配置文件的差异"
```

**响应示例:**

```json
{
  "success": true,
  "report": "文件对比分析报告...",
  "details": {
    "total_lines_file1": 100,
    "total_lines_file2": 105,
    "added_lines": 8,
    "removed_lines": 3,
    "common_lines": 92,
    "similarity_percentage": 92.5
  }
}
```

## 项目结构

```
san_bot/
├── app.py                  # Flask 主应用
├── config.py              # 配置文件
├── wechat_api.py          # 企业微信 API 封装
├── file_analyzer.py       # 文件分析核心逻辑
├── requirements.txt       # Python 依赖包
├── .env.example          # 环境变量示例
├── .gitignore            # Git 忽略文件
├── README.md             # 项目文档
└── uploads/              # 文件上传目录（自动创建）
```

## 支持的文件格式

- 文本文件: `.txt`
- CSV 文件: `.csv`
- JSON 文件: `.json`
- Excel 文件: `.xlsx`, `.xls`
- Word 文档: `.doc`, `.docx`
- PDF 文档: `.pdf`

## 分析报告内容

机器人会生成包含以下信息的详细报告：

- 📋 分析指令
- 📁 文件信息（文件名）
- 📊 对比结果
  - 各文件总行数
  - 相似度百分比
  - 新增行数
  - 删除行数
  - 相同行数
- 📝 智能结论

## 企业微信配置指南

### 1. 创建企业微信应用

1. 登录[企业微信管理后台](https://work.weixin.qq.com/)
2. 进入「应用管理」→「应用」→「创建应用」
3. 填写应用信息，上传应用logo
4. 创建成功后，记录以下信息：
   - `AgentId`（应用ID）
   - `Secret`（应用密钥）

### 2. 获取企业ID

在「我的企业」页面底部可以找到「企业ID」

### 3. 配置接收消息

1. 在应用详情页，点击「接收消息」的「设置API接收」
2. 填入回调URL: `http://your-domain.com/wechat/callback`
3. 设置 Token 和 EncodingAESKey（随机生成或自定义）
4. 保存配置

### 4. 服务器部署

确保你的服务器：
- 可以被企业微信服务器访问（公网IP或域名）
- 已开放配置的端口（默认5000）
- 支持 HTTPS（生产环境推荐）

## 开发

### 运行开发服务器

```bash
export FLASK_ENV=development
python app.py
```

### 调试模式

在 `.env` 文件中设置：
```
DEBUG=True
```

## 生产环境部署

### 使用 Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用 Docker（推荐）

创建 `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

构建和运行：

```bash
docker build -t san_bot .
docker run -p 5000:5000 --env-file .env san_bot
```

## 安全建议

1. 生产环境务必设置强密码的 `SECRET_KEY`
2. 不要将 `.env` 文件提交到代码仓库
3. 使用 HTTPS 保护数据传输
4. 定期更新依赖包版本
5. 限制上传文件大小和类型

## 故障排除

### 问题1: 企业微信回调验证失败

- 检查 Token 和 EncodingAESKey 配置是否正确
- 确认回调 URL 可以被外网访问
- 查看服务器日志获取详细错误信息

### 问题2: 文件上传失败

- 检查 `uploads/` 目录是否存在且有写入权限
- 确认文件大小不超过限制（默认16MB）
- 检查文件格式是否在支持列表中

### 问题3: Access Token 获取失败

- 验证 `WECHAT_CORP_ID` 和 `WECHAT_CORP_SECRET` 配置正确
- 检查网络连接是否正常
- 确认企业微信应用状态正常

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

## 联系方式

如有问题，请提交 Issue 或联系项目维护者。
