# 抖音视频解析服务

一个强大的抖音视频解析服务，支持多种解析策略自动切换，提供高可用性和缓存支持。

## 特性

- **多策略解析**: 支持API签名、Playwright、Selenium、Requests等多种解析策略
- **自动故障转移**: 策略失败时自动切换到备用策略
- **智能缓存**: Redis缓存减少重复解析
- **代理支持**: 支持代理池管理和自动轮换
- **监控指标**: Prometheus指标导出，支持Grafana可视化
- **速率限制**: 防止过度请求
- **Docker部署**: 一键部署，易于扩展

## 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│    Nginx    │────▶│   Flask     │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │  Strategy Manager   │
                                    └─────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
            ┌──────────────┐         ┌──────────────┐          ┌──────────────┐
            │ API Strategy │         │  Playwright  │          │   Selenium   │
            │  (X-Bogus)   │         │   Strategy   │          │   Strategy   │
            └──────────────┘         └──────────────┘          └──────────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │       Redis         │
                                    │      (Cache)        │
                                    └─────────────────────┘
```

## 快速开始

### 1. 使用Docker Compose（推荐）

```bash
# 克隆项目
git clone <repository>
cd douyin-downloader

# 复制环境变量配置
cp parsing_service/.env.example parsing_service/.env

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f parsing-service

# 停止服务
docker-compose down
```

### 2. 本地开发

```bash
# 安装依赖
cd parsing_service
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium

# 启动Redis
redis-server

# 启动服务
python app.py
```

## API文档

### 健康检查

```http
GET /health
```

响应:
```json
{
  "status": "healthy",
  "timestamp": "2024-12-28T10:00:00"
}
```

### 解析单个视频

```http
POST /parse
Content-Type: application/json

{
  "url": "https://v.douyin.com/xxxxx/",
  "use_proxy": false,
  "force_refresh": false,
  "cookies": {}
}
```

响应:
```json
{
  "success": true,
  "data": {
    "video_id": "7549035040701844779",
    "title": "视频标题",
    "author": "作者名",
    "author_id": "作者ID",
    "video_url": "https://...",
    "cover_url": "https://...",
    "duration": 30,
    "statistics": {
      "likes": 1000,
      "comments": 100,
      "shares": 50,
      "views": 10000
    }
  }
}
```

### 批量解析

```http
POST /batch_parse
Content-Type: application/json

{
  "urls": [
    "https://v.douyin.com/xxxxx/",
    "https://www.douyin.com/video/yyyyy"
  ],
  "use_proxy": false
}
```

### 获取统计信息

```http
GET /stats
```

响应:
```json
{
  "strategies": {
    "api_with_signature": {
      "enabled": true,
      "success": 100,
      "failure": 10,
      "success_rate": 0.91
    }
  },
  "cache_stats": {
    "hits": 500,
    "misses": 100,
    "hit_rate": "83.33%"
  },
  "metrics": {
    "uptime": "2h",
    "total_requests": 600,
    "success_rate": "95.00%"
  }
}
```

## 策略说明

### 1. API策略 (api_strategy.py)
- 使用X-Bogus签名算法直接调用抖音API
- 最快速但可能被反爬虫机制拦截
- 优先级: 1

### 2. Playwright策略 (playwright_strategy.py)
- 使用Playwright浏览器自动化
- 能绕过大部分反爬虫机制
- 支持拦截API响应
- 优先级: 2

### 3. Selenium策略 (selenium_strategy.py)
- 使用Selenium浏览器自动化
- 备用浏览器自动化方案
- 优先级: 3

### 4. Requests策略 (requests_strategy.py)
- 简单HTTP请求解析HTML
- 最后的备用方案
- 优先级: 4

## 配置说明

### 环境变量

编辑 `parsing_service/.env` 文件:

```env
# Flask配置
PORT=5000
FLASK_ENV=production

# Redis配置
REDIS_HOST=redis
REDIS_PORT=6379

# 策略开关
ENABLE_PLAYWRIGHT=true
ENABLE_SELENIUM=false

# 代理配置
USE_PROXY=false
PROXY_LIST=http://proxy1:8080,http://proxy2:8080

# 缓存配置
CACHE_TTL=3600
```

### 代理配置

创建 `proxies.txt` 文件:
```
http://proxy1:8080
http://user:pass@proxy2:8080
socks5://proxy3:1080
```

### Cookie配置

创建 `cookies.txt` 文件（Netscape格式）:
```
.douyin.com	TRUE	/	FALSE	1234567890	cookie_name	cookie_value
```

## 监控

### Prometheus指标

访问 `http://localhost:5000/metrics` 获取Prometheus格式的指标。

### Grafana可视化

1. 访问 `http://localhost:3000`
2. 默认用户名/密码: admin/admin
3. 添加Prometheus数据源: `http://prometheus:9090`
4. 导入仪表板模板

## 性能优化

### 1. 缓存预热

```python
import requests

# 预热常用URL
urls = [
    "https://www.douyin.com/video/xxx",
    "https://www.douyin.com/video/yyy"
]

for url in urls:
    requests.post("http://localhost:5000/parse", json={"url": url})
```

### 2. 策略权重调整

根据成功率自动调整策略权重，成功率高的策略优先使用。

### 3. 并发控制

通过环境变量 `MAX_WORKERS` 控制最大并发数。

## 故障排除

### 服务无法启动

1. 检查端口是否被占用: `lsof -i:5000`
2. 检查Redis连接: `redis-cli ping`
3. 查看日志: `docker-compose logs parsing-service`

### 解析失败

1. 检查URL格式是否正确
2. 查看具体错误信息
3. 尝试强制刷新: `force_refresh: true`
4. 检查Cookie是否过期

### 性能问题

1. 增加Redis内存: 修改 `docker-compose.yml`
2. 调整并发数: 修改 `MAX_WORKERS`
3. 启用代理池: 配置 `PROXY_LIST`

## 开发

### 添加新策略

1. 创建策略文件: `strategies/new_strategy.py`
2. 继承 `BaseStrategy` 类
3. 实现 `parse` 方法
4. 在 `app.py` 中注册策略

### 测试

```bash
# 运行测试
python test_parsing_service.py

# 测试特定策略
curl -X POST http://localhost:5000/parse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://v.douyin.com/xxxxx/"}'
```

## 许可

MIT License