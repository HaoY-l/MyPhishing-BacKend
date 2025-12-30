# MyPhishing-BacKend - AI钓鱼邮件检测网关

[![Version](https://img.shields.io/badge/version-1.0-brightgreen.svg)](https://github.com/HaoY-l/MyPhishing-BacKend)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

## 📋 项目概述

**MyPhishing-BacKend** 是一款AI驱动的钓鱼邮件检测网关，通过多源威胁情报集成、机器学习模型和沙箱分析，实现对钓鱼邮件的智能识别、告警和拦截。

### 核心功能

- 🔍 **多源威胁情报集成**：VirusTotal、微步在线等
- 🎯 **智能邮件分析**：来源IP、域名、URL、附件、内容关键字威胁识别
- 📊 **本地知识库学习**：持续学习和优化检测模型
- 🚫 **自动拦截告警**：可疑/钓鱼邮件实时拦截和告警
- 🔄 **邮件网关转发**：透明集成到邮件系统

### 适用人群

- 后端开发
- 运维人员
- 安全人员

## 🛠️ 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 开发语言 | Python | 3.8+ |
| Web框架 | Flask / FastAPI | - |
| 数据存储 | MySQL / Chroma | - |
| 消息队列 | Redis | - |
| 服务器 | Gunicorn | - |
| 容器化 | Docker / Docker Compose | - |

## 📁 项目结构

```
MyPhishing/
├── app.py                      # 后端启动入口（WSGI/ASGI）
├── config/                     # 配置目录
│   ├── settings.py            # 核心配置文件
│   └── config.json            # 系统变量配置
├── data/                       # 数据目录
│   ├── logs/                  # 日志文件
│   ├── temp/                  # 临时文件
│   └── bge-small/             # Embedding模型
├── src/                        # 核心业务代码
│   ├── api/                   # 接口路由层
│   ├── service/               # 业务逻辑层
│   ├── model/                 # 数据模型层
│   └── utils/                 # 工具函数层
├── chroma_db/                 # 向量库目录（自动生成）
├── requirements.txt           # 依赖清单
├── .env                       # 环境变量配置
├── docker-compose.yml         # Docker编排文件
└── start.sh                   # 启动脚本
```

## 🚀 快速开始

### 前置条件

```bash
# 检查Python版本
python3 --version 

# 检查已安装MySQL并创建空数据库
# 数据库名建议：myphishing
```

### 环境安装

#### 1. 克隆仓库

```bash
git clone https://github.com/HaoY-l/MyPhishing-BacKend.git
cd MyPhishing-BacKend
```

#### 2. 创建虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt

# 如果内存不足（如2C2G），使用轻量级PyTorch替代品
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 下载Embedding模型 (bge-small)
huggingface-cli download BAAI/bge-small-en-v1.5 \
  --local-dir ./data/bge-small \
  --local-dir-use-symlinks False
```

### 配置修改

#### 1. 系统配置 (`config/config.json`)

```json
{
  "EMAIL_INTERCEPT_ENABLED_1": true,
  "EMAIL_ALERT_ENABLED_1": true,
  "EMAIL_INTERCEPT_ENABLED_2": true,
  "EMAIL_ALERT_ENABLED_2": true,
  "NOTIFICATION_EMAIL": "example@xx.com"
}
```

**配置说明：**

| 参数 | 说明 |
|------|------|
| `EMAIL_INTERCEPT_ENABLED_1` | 可疑邮件是否拦截（true/false） |
| `EMAIL_ALERT_ENABLED_1` | 可疑邮件是否告警（true/false） |
| `EMAIL_INTERCEPT_ENABLED_2` | 钓鱼邮件是否拦截（true/false） |
| `EMAIL_ALERT_ENABLED_2` | 钓鱼邮件是否告警（true/false） |
| `NOTIFICATION_EMAIL` | 告警通知邮箱 |

#### 2. 环境变量配置 (`.env`)

```bash
# ============ Flask 应用配置 ============
FLASK_HOST=0.0.0.0
FLASK_PORT=8000

# ============ SMTP 邮件网关配置 ============
SMTP_LISTEN_HOST=0.0.0.0           # 网关监听地址
SMTP_LISTEN_PORT=25                # 网关监听端口
SMTP_RELAY_HOST=218.xxx.xxx.xxx    # 邮件服务器地址
SMTP_RELAY_PORT=2525               # 邮件服务器端口

# ============ 域名配置 ============
MY_EMAIL_DOMAINS=xxx.cc            # 多个域名用逗号分隔，不要有空格

# ============ 限流配置 ============
GATEWAY_RATE_LIMIT=10              # 每分钟同一IP的最大请求数
GATEWAY_BLOCK_DURATION=600         # 超限后的阻止时长（秒）

# ============ 检测配置 ============
DETECTION_WORKERS=10               # Worker进程数（建议：CPU核心数 * 2~4）
DETECTION_QUEUE_SIZE=1000          # 邮件队列最大长度

# ============ MySQL 数据库配置 ============
MYSQL_HOST=218.xxx.xxx.xxx
MYSQL_PORT=3340
MYSQL_USER=root
MYSQL_PASSWORD=xxxxxxx
MYSQL_DATABASE=myphishing

# ============ Redis 配置 ============
# 开发环境
REDIS_URL=redis://localhost:6379/0

# Docker环境
# REDIS_URL=redis://redis:6379/0

# ============ 威胁情报API配置 ============
# VirusTotal
VIRUSTOTAL_API_KEY=77102xxxxxxx068f

# 微步在线
THREATBOOK_API_KEY=1b9ab1xxxxxxxxdf3f
DEFAULT_SANDBOX_TYPE=win7_sp1_enx86_office2013
DEFAULT_RUN_TIME=60

# ============ AI模型配置 ============
DEEPSEEK_API_KEY=sk-69b81xxxxxxxxx9d4
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL_NAME=deepseek-chat
```

### 启动服务

#### 开发环境启动

```bash
# 1. 启动Redis
docker pull redis
docker run -itd -p 6379:6379 redis

# 2. 修改.env的Redis连接地址
# REDIS_URL=redis://localhost:6379/0

# 3. 执行启动脚本
./start.sh
```

**启动成功日志示例：**

```
🖥️  检测到宿主机环境
🧹 清理端口...
🚀 执行系统初始化...
2025-12-26 17:19:10,762 [INFO] 🚀 系统初始化开始
2025-12-26 17:19:10,822 [INFO] ✅ email_data 表已处理
2025-12-26 17:19:10,829 [INFO] ✅ data_version 表已处理
2025-12-26 17:19:10,829 [INFO] 🎉 数据库表结构初始化/验证完成！
2025-12-26 17:19:11,333 [INFO] ✅ Embedding 模型加载成功
2025-12-26 17:19:11,975 [INFO] ✅ Chroma 客户端初始化成功
2025-12-26 17:19:11,975 [INFO] 🎉 系统初始化完成
🚀 启动 Celery...
🚀 启动 SMTP...
🚀 启动 API (Gunicorn)...
✅ 所有服务已启动
📜 日志：tail -f celery.log flask.log gateway.log
```

#### 生产环境启动（Docker）

```bash
# 1. 构建镜像（首次）
nohup docker compose --progress=plain build backend --no-cache > build.log 2>&1 &

# 2. 查看构建日志
tail -f build.log

# 3. 清理构建缓存（可选）
docker builder prune -af

# 4. 启动容器
docker-compose up -d

# 5. 查看容器日志
docker logs <容器ID>
```

### 查看日志

```bash
# 查看所有日志
tail -f celery.log flask.log gateway.log

# 查看特定日志
tail -f celery.log    # Celery任务日志
tail -f flask.log     # Flask API日志
tail -f gateway.log   # SMTP网关日志
```

## 📧 邮件解析设置

### 场景一：网关与邮件服务器分离（推荐）

1. **修改DNS MX记录**，指向AI钓鱼邮件检测网关
2. **配置.env**：
   ```bash
   SMTP_LISTEN_PORT=25          # 网关监听25端口
   SMTP_RELAY_PORT=25           # 转发到邮件服务器的25端口
   ```

### 场景二：网关与邮件服务器同机（不推荐）

1. **修改DNS MX记录**，指向AI钓鱼邮件检测网关
2. **配置.env**：
   ```bash
   SMTP_LISTEN_PORT=25          # 网关监听25端口
   SMTP_RELAY_PORT=2525         # 邮件服务器监改为2525（避免端口冲突）
   ```

## 🔒 防火墙端口配置

开放以下端口（根据实际部署情况调整）：

```
邮件协议端口：
  25    - SMTP协议（邮件发送）
  110   - POP3协议（邮件接收）
  143   - IMAP协议（邮件访问）
  465   - SMTP over SSL
  587   - SMTP TLS端口
  993   - IMAP over SSL

应用服务：
  3000  - 前端应用
  8000  - 后端API

Web服务（可选）：
  80    - HTTP
  443   - HTTPS
```

## 📊 工作流程

```
互联网邮件
    │
    ▼
┌─────────────────────────────────┐
│ AI钓鱼邮件检测网关             │
│ ├─ 邮件解析                    │
│ ├─ 威胁情报检测               │
│ │  ├─ VirusTotal              │
│ │  ├─ 微步在线                │
│ │  └─ 本地知识库              │
│ ├─ AI模型分析                 │
│ │  └─ DeepSeek + Embedding    │
│ ├─ 风险评估                    │
│ └─ 拦截/告警决策              │
└─────────────────────────────────┘
    │
    ▼
企业自建邮件服务器（允许/拒收）
    │
    ▼
用户邮箱
```

## 📝 环境变量详解

### Flask应用
- `FLASK_HOST`: 监听地址（通常0.0.0.0）
- `FLASK_PORT`: 监听端口（默认8000）

### SMTP网关
- `SMTP_LISTEN_HOST`: 网关对外监听地址
- `SMTP_LISTEN_PORT`: 网关监听端口（通常25）
- `SMTP_RELAY_HOST`: 后端邮件服务器IP
- `SMTP_RELAY_PORT`: 后端邮件服务器端口

### 数据库
- `MYSQL_HOST`: MySQL服务器地址
- `MYSQL_PORT`: MySQL端口（默认3306或3340）
- `MYSQL_USER`: 数据库用户
- `MYSQL_PASSWORD`: 数据库密码
- `MYSQL_DATABASE`: 数据库名（建议：myphishing）

### 缓存
- `REDIS_URL`: Redis连接字符串

### 威胁情报
- `VIRUSTOTAL_API_KEY`: VirusTotal API密钥
- `THREATBOOK_API_KEY`: 微步在线API密钥
- `DEFAULT_SANDBOX_TYPE`: 沙箱类型（如win7_sp1_enx86_office2013）
- `DEFAULT_RUN_TIME`: 沙箱运行时间（秒）

### AI模型
- `DEEPSEEK_API_KEY`: DeepSeek API密钥
- `DEEPSEEK_API_ENDPOINT`: DeepSeek API端点
- `DEEPSEEK_MODEL_NAME`: 模型名称（deepseek-chat）

## 🔧 常见问题

### Q1: 内存不足怎么办？
**A:** 使用轻量级PyTorch版本：
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### Q2: 网关与邮件服务器在同一台机器怎么配置？
**A:** 参考[邮件解析设置](#邮件解析设置)的场景二，修改邮件服务器监听端口避免冲突。

### Q3: 如何修改告警邮箱？
**A:** 修改`config/config.json`中的`NOTIFICATION_EMAIL`字段。

### Q4: Docker启动失败怎么办？
**A:** 检查以下几点：
- Docker和Docker Compose已安装
- 磁盘空间充足（镜像较大）
- 防火墙未阻止端口访问
- 查看详细日志：`docker logs <容器ID>`

### Q5: 如何调整Worker进程数？
**A:** 修改`.env`中的`DETECTION_WORKERS`（建议值：CPU核心数 × 2~4）

## 📚 文档与支持

- **官网地址**: https://hyinfo.cc/
- **文档地址**: https://www.yuque.com/weare/qqlqbo/xcggcv1oya9fdcai?singleDoc# 《MyPhishing-BacKen用户手册》
- **版本**: 1.0.0
- **更新日期**: 2025-12-30

## 📄 许可证

MIT License - 详见LICENSE文件

---

**最后更新**: 2025-12-30  
**维护者**: 微信：tomorrow_me-