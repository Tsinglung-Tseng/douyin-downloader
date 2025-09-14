# 抖音下载器使用指南

## 架构说明

本项目包含三个版本的下载器：

1. **V1 (DouYinCommand.py)**: 原始版本，直接调用API
2. **V2 (downloader_v2.py)**: 增强版，支持Cookie管理和批量下载
3. **V3 (downloader_v3.py + 解析服务)**: 最新版，使用独立解析服务

### 推荐架构（V3）

```
┌─────────────────┐           ┌──────────────────┐
│ downloader_v3.py│ ────────> │  Parsing Service │
│   (下载客户端)   │           │   (解析服务)      │
└─────────────────┘           └──────────────────┘
        │                              │
        │                              ├── API Strategy (X-Bogus)
        ▼                              ├── Playwright Strategy
    [下载文件]                          ├── Selenium Strategy
                                      └── Requests Strategy
```

## 快速开始

### 方式1：使用Docker（推荐）

```bash
# 1. 启动解析服务
docker-compose up -d

# 2. 等待服务启动（约30秒）
docker-compose logs -f parsing-service

# 3. 使用下载器
python downloader_v3.py https://v.douyin.com/xxxxx/
```

### 方式2：本地运行

```bash
# 终端1：启动Redis
redis-server

# 终端2：启动解析服务
cd parsing_service
pip install -r requirements.txt
python app.py

# 终端3：使用下载器
pip install requests tqdm aiohttp
python downloader_v3.py https://v.douyin.com/xxxxx/
```

## 使用示例

### 1. 下载单个视频

```bash
# 短链接
python downloader_v3.py https://v.douyin.com/gNv_ZvhuEr0/

# 完整链接
python downloader_v3.py https://www.douyin.com/video/7549035040701844779
```

### 2. 批量下载

```bash
# 多个URL
python downloader_v3.py \
  https://v.douyin.com/xxx/ \
  https://v.douyin.com/yyy/ \
  https://v.douyin.com/zzz/

# 从文件读取
cat urls.txt | xargs python downloader_v3.py
```

### 3. 交互模式

```bash
# 启动交互模式
python downloader_v3.py -i

# 或直接运行
python downloader_v3.py
```

交互模式下可以：
- 逐个输入URL下载
- 输入多个URL（空格或逗号分隔）批量下载
- 输入 `stats` 查看统计
- 输入 `q` 退出

### 4. 使用Cookie（提高成功率）

```bash
# 1. 导出Cookie（使用浏览器插件导出为Netscape格式）
# 2. 使用Cookie文件
python downloader_v3.py -c cookies.txt https://v.douyin.com/xxx/
```

### 5. 高级选项

```bash
# 指定解析服务地址
python downloader_v3.py -s http://192.168.1.100:5000 URL

# 指定输出目录
python downloader_v3.py -o /path/to/save URL

# 使用代理
python downloader_v3.py --proxy URL

# 强制刷新（不使用缓存）
python downloader_v3.py --force URL

# 设置并发数
python downloader_v3.py -m 10 URL1 URL2 URL3
```

## Cookie获取方法

### 方法1：浏览器插件

1. 安装Cookie导出插件（如 EditThisCookie、Cookie-Editor）
2. 登录抖音网页版
3. 导出Cookie为Netscape格式
4. 保存为 `cookies.txt`

### 方法2：浏览器开发者工具

1. 打开抖音网页版并登录
2. F12打开开发者工具
3. Network标签 → 找到请求 → Headers → Cookie
4. 复制Cookie字符串
5. 转换为Netscape格式保存

### 方法3：自动提取（V2版本）

```bash
# downloader_v2.py 支持从浏览器自动提取
python downloader_v2.py --extract-cookies chrome
```

## 配置优化

### 1. 解析服务配置

编辑 `parsing_service/.env`:

```env
# 启用更多策略
ENABLE_PLAYWRIGHT=true
ENABLE_SELENIUM=true

# 增加缓存时间
CACHE_TTL=7200

# 使用代理池
USE_PROXY=true
PROXY_LIST=http://proxy1:8080,http://proxy2:8080
```

### 2. 性能优化

```bash
# 增加并发数
python downloader_v3.py -m 10 URL1 URL2 URL3

# Docker资源限制
docker-compose up -d --scale parsing-service=3
```

### 3. 代理配置

创建 `parsing_service/proxies.txt`:

```
http://proxy1:8080
http://user:pass@proxy2:8080
socks5://proxy3:1080
```

## 故障排除

### 问题1：解析服务无法连接

```bash
# 检查服务状态
docker-compose ps

# 查看日志
docker-compose logs parsing-service

# 重启服务
docker-compose restart parsing-service
```

### 问题2：解析失败

1. 检查网络连接
2. 尝试使用Cookie
3. 启用代理
4. 强制刷新缓存

```bash
python downloader_v3.py -c cookies.txt --force --proxy URL
```

### 问题3：下载速度慢

1. 增加并发数
2. 使用更快的代理
3. 优化网络连接

### 问题4：视频无法播放

可能是无水印链接失效，尝试：
1. 强制刷新获取新链接
2. 使用不同的解析策略

## 监控和统计

### 1. 查看统计信息

```bash
# 在交互模式中
> stats

# 或通过API
curl http://localhost:5000/stats
```

### 2. Grafana可视化

访问 http://localhost:3000
- 用户名: admin
- 密码: admin

### 3. 查看指标

```bash
curl http://localhost:5000/metrics
```

## API使用

如果你想在自己的程序中使用解析服务：

```python
import requests

# 解析单个视频
response = requests.post('http://localhost:5000/parse', json={
    'url': 'https://v.douyin.com/xxx/',
    'use_proxy': False,
    'force_refresh': False
})

if response.status_code == 200:
    data = response.json()
    if data['success']:
        video_info = data['data']
        print(f"标题: {video_info['title']}")
        print(f"视频URL: {video_info['video_url']}")
```

## 注意事项

1. **合理使用**: 请勿用于商业用途，仅供学习交流
2. **频率控制**: 避免频繁请求，建议间隔1-2秒
3. **Cookie更新**: Cookie可能过期，需要定期更新
4. **代理质量**: 使用高质量代理可以提高成功率
5. **资源管理**: Docker运行需要足够的内存和CPU

## 版本对比

| 特性 | V1 | V2 | V3 |
|-----|----|----|-----|
| 基础下载 | ✅ | ✅ | ✅ |
| Cookie支持 | ❌ | ✅ | ✅ |
| 批量下载 | ❌ | ✅ | ✅ |
| 自动重试 | ❌ | ✅ | ✅ |
| 解析服务 | ❌ | ❌ | ✅ |
| 多策略切换 | ❌ | ❌ | ✅ |
| 缓存支持 | ❌ | ❌ | ✅ |
| 监控指标 | ❌ | ❌ | ✅ |
| Docker部署 | ❌ | ❌ | ✅ |

## 开发扩展

如需添加新功能或策略，请参考 [parsing_service/README.md](parsing_service/README.md)