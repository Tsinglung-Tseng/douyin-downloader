# 抖音下载器 - 无水印批量下载工具

![douyin-downloader](https://socialify.git.ci/jiji262/douyin-downloader/image?custom_description=%E6%8A%96%E9%9F%B3%E6%89%B9%E9%87%8F%E4%B8%8B%E8%BD%BD%E5%B7%A5%E5%85%B7%EF%BC%8C%E5%8E%BB%E6%B0%B4%E5%8D%B0%EF%BC%8C%E6%94%AF%E6%8C%81%E8%A7%86%E9%A2%91%E3%80%81%E5%9B%BE%E9%9B%86%E3%80%81%E5%90%88%E9%9B%86%E3%80%81%E9%9F%B3%E4%B9%90%28%E5%8E%9F%E5%A3%B0%29%E3%80%82%0A%E5%85%8D%E8%B4%B9%EF%BC%81%E5%85%8D%E8%B4%B9%EF%BC%81%E5%85%8D%E8%B4%B9%EF%BC%81&description=1&font=Jost&forks=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fjiji262%2Fdouyin-downloader%2Frefs%2Fheads%2Fmain%2Fimg%2Flogo.png&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Light)

一个功能强大的抖音内容批量下载工具，支持视频、图集、音乐、直播等多种内容类型的下载。提供三个版本工具和一个独立的解析服务。

## 📋 目录

- [项目架构](#项目架构)
- [快速开始](#快速开始)
- [工具详细说明](#工具详细说明)
- [使用步骤](#使用步骤)
- [Cookie获取方法](#cookie获取方法)
- [故障排除](#故障排除)
- [开发说明](#开发说明)

## 🏗️ 项目架构

```
douyin-downloader/
├── 下载器工具/
│   ├── DouYinCommand.py      # V1: 原始版本（简单直接）
│   ├── downloader_v2.py      # V2: 增强版（独立运行）
│   └── downloader_v3.py      # V3: 最新版（配合解析服务）
│
├── 解析服务/
│   └── parsing_service/      # Docker化的解析服务
│       ├── app.py            # Flask主服务
│       ├── strategies/       # 多种解析策略
│       │   ├── api_strategy.py        # API + X-Bogus签名
│       │   ├── playwright_strategy.py # Playwright浏览器自动化
│       │   ├── selenium_strategy.py   # Selenium浏览器自动化
│       │   └── requests_strategy.py   # 简单HTTP请求
│       └── utils/           # 工具模块
│           ├── cache_manager.py    # Redis缓存管理
│           ├── proxy_manager.py    # 代理池管理
│           └── metrics_collector.py # 性能指标收集
│
├── 辅助工具/
│   ├── xbogus_generator.py   # X-Bogus签名生成
│   ├── get_cookie.py         # Cookie提取工具
│   └── test_*.py            # 测试脚本
│
└── 配置文件/
    ├── docker-compose.yml    # Docker编排
    ├── requirements.txt      # Python依赖
    └── cookies.txt          # Cookie文件（需创建）
```

## 🚀 快速开始

### 环境要求

- **Python 3.9+**
- **操作系统**：Windows、macOS、Linux
- **Docker**（V3版本需要）

### 方式1：最简单使用（V1版本）

```bash
# 安装基础依赖
pip install requests

# 下载单个视频
python DouYinCommand.py https://v.douyin.com/xxxxx/
```

### 方式2：独立使用（V2版本）

```bash
# 安装依赖
pip install requests aiohttp tqdm browser-cookie3

# 下载视频
python downloader_v2.py https://v.douyin.com/xxxxx/

# 交互模式
python downloader_v2.py -i
```

### 方式3：生产环境（V3版本 + 解析服务）⭐推荐

```bash
# 1. 启动解析服务
docker-compose up -d

# 2. 使用下载器
python downloader_v3.py https://v.douyin.com/xxxxx/
```

## 📖 工具详细说明

### 1️⃣ DouYinCommand.py（V1 - 基础版）

**特点**：
- ✅ 无需配置，开箱即用
- ✅ 代码简单，易于理解
- ❌ 功能有限，成功率较低
- ❌ 不支持批量下载

**详细使用步骤**：

#### 步骤1：准备配置文件

```bash
# 复制示例配置
cp config_douyin_example.yml config_douyin.yml

# 编辑配置文件
vim config_douyin.yml
```

#### 步骤2：配置Cookie

```yaml
# config_douyin.yml
cookies:
  msToken: xxx      # 必需
  ttwid: xxx       # 必需
  sessionid: xxx   # 登录状态（下载用户主页必需）
```

#### 步骤3：运行下载

```bash
# 基本运行
python DouYinCommand.py

# 指定配置文件
python DouYinCommand.py -c custom_config.yml

# 命令行模式
python DouYInCommand.py --cmd
```

**适用场景**：
- 临时下载几个视频
- 测试URL是否有效
- 学习代码结构

---

### 2️⃣ downloader_v2.py（V2 - 增强版）

**特点**：
- ✅ 支持自动提取浏览器Cookie
- ✅ 批量下载功能
- ✅ 交互模式友好
- ✅ 独立运行，无需其他服务
- ⭐ 中等成功率

**详细使用步骤**：

#### 步骤1：安装依赖

```bash
pip install requests aiohttp tqdm browser-cookie3 rich
```

#### 步骤2：准备Cookie（可选但推荐）

```bash
# 方法A：自动从浏览器提取
python downloader_v2.py --extract-cookies chrome

# 方法B：手动创建cookies.txt
# 1. 登录抖音网页版
# 2. 使用浏览器插件导出Cookie
# 3. 保存为cookies.txt（Netscape格式）
```

#### 步骤3：使用下载器

```bash
# 单个视频下载
python downloader_v2.py https://v.douyin.com/xxxxx/

# 批量下载（多个URL）
python downloader_v2.py url1 url2 url3

# 交互模式（推荐新手）
python downloader_v2.py -i
# 然后按提示操作：
# - 输入单个URL下载
# - 输入多个URL批量下载（空格分隔）
# - 输入 'stats' 查看统计
# - 输入 'q' 退出

# 高级选项
python downloader_v2.py \
  -c cookies.txt \       # 使用Cookie文件
  -o downloads \         # 指定输出目录
  -m 10 \               # 设置并发数
  --proxy \             # 使用代理
  url1 url2
```

#### 步骤4：处理不同类型的URL

```bash
# 短链接
python downloader_v2.py https://v.douyin.com/xxxxx/

# 视频链接
python downloader_v2.py https://www.douyin.com/video/7549035040701844779

# 用户主页（下载该用户的视频）
python downloader_v2.py https://www.douyin.com/user/MS4wLjABAAAAxxxxx

# 合集链接
python downloader_v2.py https://www.douyin.com/collection/xxxxx

# 音乐链接（下载使用该音乐的视频）
python downloader_v2.py https://www.douyin.com/music/xxxxx
```

**适用场景**：
- 日常批量下载
- 不想配置Docker
- 需要快速使用

---

### 3️⃣ downloader_v3.py + 解析服务（V3 - 生产版）⭐最推荐

**特点**：
- ✅ 最高成功率（多策略自动切换）
- ✅ Redis缓存（避免重复解析）
- ✅ 支持监控和统计
- ✅ Docker化部署
- ✅ 可扩展性强
- ⭐ 需要运行解析服务

**详细使用步骤**：

#### 步骤1：安装Docker（如未安装）

```bash
# macOS
brew install docker docker-compose

# Ubuntu/Debian
sudo apt-get install docker.io docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### 步骤2：配置解析服务

```bash
# 1. 复制环境变量配置
cp parsing_service/.env.example parsing_service/.env

# 2. 编辑配置（可选）
vim parsing_service/.env
# 主要配置项：
# - ENABLE_PLAYWRIGHT=true  # 启用Playwright策略
# - CACHE_TTL=3600          # 缓存时间
# - MAX_WORKERS=10          # 并发数
```

#### 步骤3：启动解析服务

```bash
# 启动所有服务（Redis + 解析服务 + Nginx）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f parsing-service

# 等待服务就绪（约30秒）
curl http://localhost:5000/health
```

#### 步骤4：使用下载器

```bash
# 安装客户端依赖
pip install requests aiohttp tqdm

# 基础使用
python downloader_v3.py https://v.douyin.com/xxxxx/

# 批量下载
python downloader_v3.py url1 url2 url3

# 交互模式
python downloader_v3.py -i

# 高级选项
python downloader_v3.py \
  -s http://localhost:5000 \  # 解析服务地址
  -c cookies.txt \            # Cookie文件
  -o downloads \              # 输出目录
  -m 10 \                    # 并发数
  --proxy \                  # 使用代理
  --force \                  # 强制刷新缓存
  url1 url2
```

#### 步骤5：监控和管理

```bash
# 查看统计信息
curl http://localhost:5000/stats | jq

# 查看Prometheus指标
curl http://localhost:5000/metrics

# 访问Grafana监控面板
open http://localhost:3000
# 默认账号：admin/admin

# 清除缓存
curl -X POST http://localhost:5000/clear_cache

# 停止服务
docker-compose down

# 停止并删除数据
docker-compose down -v
```

**适用场景**：
- 大量视频下载
- 需要高成功率
- 长期运行的服务
- 团队共享使用

---

## 🔄 解析服务架构说明

V3版本使用独立的解析服务，提供多策略自动切换：

```
用户请求
    ↓
Flask API服务
    ↓
策略管理器（按权重排序）
    ↓
┌──────────────────────────────────────┐
│  1. API策略（X-Bogus签名）            │ ← 最快但可能被拦截
│  2. Playwright策略（浏览器自动化）     │ ← 成功率高
│  3. Selenium策略（备用浏览器）         │ ← 备用方案
│  4. Requests策略（HTML解析）          │ ← 最后尝试
└──────────────────────────────────────┘
    ↓
Redis缓存（避免重复解析）
    ↓
返回视频信息
```

### 策略详细说明

| 策略 | 优先级 | 成功率 | 速度 | 说明 |
|-----|--------|--------|------|------|
| API + X-Bogus | 1 | 中 | 快 | 使用签名算法直接调用API |
| Playwright | 2 | 高 | 慢 | 模拟真实浏览器行为 |
| Selenium | 3 | 高 | 慢 | 备用浏览器自动化 |
| Requests | 4 | 低 | 快 | 简单HTTP请求解析HTML |

---

## 🍪 Cookie获取方法

Cookie可以显著提高下载成功率，以下是获取方法：

### 方法1：浏览器插件（推荐）

1. **安装Cookie编辑器插件**
   - Chrome: EditThisCookie 或 Cookie-Editor
   - Firefox: Cookie Quick Manager

2. **登录抖音网页版**
   - 访问 https://www.douyin.com
   - 使用手机扫码登录

3. **导出Cookie**
   - 点击插件图标
   - 选择"导出" → "Netscape格式"
   - 保存为 `cookies.txt`

### 方法2：浏览器开发者工具

1. 登录抖音网页版
2. 按F12打开开发者工具
3. 切换到Network标签
4. 刷新页面
5. 找到任意请求 → Headers → Cookie
6. 复制整个Cookie字符串

### 方法3：自动提取（仅V2支持）

```bash
# 从Chrome提取
python downloader_v2.py --extract-cookies chrome

# 从Edge提取
python downloader_v2.py --extract-cookies edge

# 从Firefox提取
python downloader_v2.py --extract-cookies firefox
```

### 方法4：使用辅助工具

```bash
# 使用Cookie提取工具
python get_cookie.py

# 手动登录获取Cookie
python manual_login_cookie.py
```

### Cookie字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| msToken | ✅ | API访问令牌 |
| ttwid | ✅ | 设备标识 |
| sessionid | ⚠️ | 登录状态（下载用户主页必需） |
| odin_tt | ❌ | 提高成功率 |
| passport_csrf_token | ❌ | CSRF保护 |

---

## 🔧 故障排除

### 问题1：解析失败/下载失败

**可能原因**：
- Cookie过期或无效
- 网络问题
- 抖音反爬虫升级

**解决方案**：
```bash
# 1. 更新Cookie
python get_cookie.py

# 2. 使用V3版本（成功率更高）
docker-compose up -d
python downloader_v3.py URL

# 3. 启用代理
python downloader_v3.py --proxy URL

# 4. 强制刷新缓存
python downloader_v3.py --force URL
```

### 问题2：Docker服务启动失败

```bash
# 检查端口占用
lsof -i:5000
lsof -i:6379

# 查看错误日志
docker-compose logs

# 重新构建
docker-compose build --no-cache
docker-compose up -d
```

### 问题3：视频无法播放

**可能原因**：
- 下载不完整
- 视频格式问题

**解决方案**：
```bash
# 重新下载
python downloader_v3.py --force URL

# 检查文件完整性
ffmpeg -i video.mp4 -f null -
```

### 问题4："No module named 'xxx'"

```bash
# 安装缺失的依赖
pip install -r requirements.txt

# 或单独安装
pip install requests aiohttp tqdm
```

---

## 🛠️ 开发说明

### 项目文件说明

| 文件 | 用途 | 状态 |
|------|------|------|
| DouYinCommand.py | V1原始版本 | ✅ 保留 |
| downloader_v2.py | V2增强版 | ✅ 使用 |
| downloader_v3.py | V3客户端 | ✅ 推荐 |
| parsing_service/ | 解析服务 | ✅ 核心 |
| xbogus_generator.py | 签名生成 | ✅ 依赖 |
| get_cookie.py | Cookie工具 | ✅ 辅助 |
| test_*.py | 测试脚本 | ✅ 测试 |
| downloader.py | 过渡版本 | ❌ 可删除 |

### 添加新的解析策略

1. **创建策略文件**
```python
# parsing_service/strategies/new_strategy.py
from .base_strategy import BaseStrategy

class NewStrategy(BaseStrategy):
    async def parse(self, url: str, options: Dict = None) -> Dict:
        # 实现解析逻辑
        pass
```

2. **注册策略**
```python
# parsing_service/app.py
strategies.append({
    'name': 'new_strategy',
    'handler': NewStrategy(),
    'priority': 5,
    'enabled': True
})
```

### 运行测试

```bash
# 测试V2版本
python test_downloader_v2.py

# 测试解析服务
python test_parsing_service.py

# 测试签名算法
python test_with_signature.py
```

---

## 📊 版本对比

| 功能 | V1 | V2 | V3 |
|-----|----|----|-----|
| 单视频下载 | ✅ | ✅ | ✅ |
| 批量下载 | ❌ | ✅ | ✅ |
| Cookie管理 | ❌ | ✅ | ✅ |
| 浏览器Cookie提取 | ❌ | ✅ | ❌ |
| 交互模式 | ❌ | ✅ | ✅ |
| 多策略解析 | ❌ | ❌ | ✅ |
| 缓存支持 | ❌ | ❌ | ✅ |
| Docker部署 | ❌ | ❌ | ✅ |
| 监控统计 | ❌ | ⭕ | ✅ |
| 成功率 | 低 | 中 | 高 |
| 使用难度 | 简单 | 简单 | 中等 |

---

## 📝 实际使用案例

### 案例1：下载单个视频

```bash
# V1版本
python DouYinCommand.py

# V2版本
python downloader_v2.py https://v.douyin.com/xxxxx/

# V3版本（需先启动服务）
docker-compose up -d
python downloader_v3.py https://v.douyin.com/xxxxx/
```

### 案例2：批量下载用户视频

```bash
# V2版本 - 交互模式
python downloader_v2.py -i
> https://www.douyin.com/user/xxxxx
> stats  # 查看进度

# V3版本 - 命令行模式
python downloader_v3.py \
  https://www.douyin.com/user/xxxxx \
  -o ./user_videos \
  -m 10
```

### 案例3：定时任务脚本

```bash
#!/bin/bash
# daily_download.sh
cd /path/to/douyin-downloader

# 启动解析服务（如果未运行）
docker-compose up -d

# 等待服务就绪
sleep 10

# 下载指定用户的新视频
python downloader_v3.py \
  https://www.douyin.com/user/xxxxx \
  -c cookies.txt \
  --force

# 查看统计
curl http://localhost:5000/stats
```

---

## ⚖️ 注意事项

1. **合理使用**：仅供学习交流，请勿用于商业用途
2. **频率控制**：避免频繁请求，建议间隔1-2秒
3. **Cookie更新**：Cookie会过期，需要定期更新
4. **资源占用**：V3版本需要较多系统资源（Docker）
5. **网络要求**：确保网络稳定，必要时使用代理

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可

MIT License