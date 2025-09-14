#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音下载器 - 统一增强版
支持视频、图文、用户主页、合集等多种内容的批量下载
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import argparse
import yaml

# 第三方库
try:
    import aiohttp
    import requests
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich import print as rprint
except ImportError as e:
    print(f"请安装必要的依赖: pip install aiohttp requests rich pyyaml")
    sys.exit(1)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入项目模块
from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls
from apiproxy.douyin.result import Result
from apiproxy.common.utils import Utils
from apiproxy.douyin.auth.cookie_manager import AutoCookieManager
from apiproxy.douyin.auth.signature_generator import get_x_bogus, get_a_bogus
from apiproxy.douyin.database import DataBase

# 配置日志 - 只记录到文件，不输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 控制台日志级别设置为WARNING，减少干扰
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
        handler.setLevel(logging.WARNING)

# Rich console
console = Console()


class ContentType:
    """内容类型枚举"""
    VIDEO = "video"
    IMAGE = "image" 
    USER = "user"
    MIX = "mix"
    MUSIC = "music"
    LIVE = "live"


class DownloadStats:
    """下载统计"""
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
    
    @property
    def success_rate(self):
        return (self.success / self.total * 100) if self.total > 0 else 0
    
    @property
    def elapsed_time(self):
        return time.time() - self.start_time
    
    def to_dict(self):
        return {
            'total': self.total,
            'success': self.success,
            'failed': self.failed,
            'skipped': self.skipped,
            'success_rate': f"{self.success_rate:.1f}%",
            'elapsed_time': f"{self.elapsed_time:.1f}s"
        }


class RateLimiter:
    """速率限制器"""
    def __init__(self, max_per_second: float = 2):
        self.max_per_second = max_per_second
        self.min_interval = 1.0 / max_per_second
        self.last_request = 0
    
    async def acquire(self):
        """获取许可"""
        current = time.time()
        time_since_last = current - self.last_request
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)
        self.last_request = time.time()


class RetryManager:
    """重试管理器"""
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_delays = [1, 2, 5]  # 重试延迟
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """执行函数并自动重试"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(f"第 {attempt + 1} 次尝试失败: {e}, {delay}秒后重试...")
                    await asyncio.sleep(delay)
        raise last_error


class UnifiedDownloader:
    """统一下载器"""

    def __init__(self, config_path: str = "config_downloader.yml"):
        self.config = self._load_config(config_path)
        self.urls_helper = Urls()
        self.result_helper = Result()
        self.utils = Utils()

        # 组件初始化
        self.stats = DownloadStats()
        self.rate_limiter = RateLimiter(max_per_second=2)
        self.retry_manager = RetryManager(max_retries=self.config.get('retry_times', 3))

        # msToken和签名相关
        self.mstoken = self._generate_mstoken()
        self.device_id = self._generate_device_id()
        
        # Cookie与请求头（延迟初始化，支持自动获取）
        self.cookies = self.config.get('cookies') if 'cookies' in self.config else self.config.get('cookie')

        # 检测Cookie配置类型
        self.auto_cookie = bool(self.config.get('auto_cookie')) or (isinstance(self.config.get('cookie'), str) and self.config.get('cookie') == 'auto') or (isinstance(self.config.get('cookies'), str) and self.config.get('cookies') == 'auto')

        # 检测browser-cookies模式（yt-dlp方式）
        self.browser_cookie = None
        if isinstance(self.cookies, str) and self.cookies.startswith('browser:'):
            # 格式: browser:chrome 或 browser:edge 等
            self.browser_cookie = self.cookies.split(':', 1)[1] if ':' in self.cookies else 'chrome'
            self.cookies = None  # 稍后从浏览器获取

        self.headers = {**douyin_headers}
        # 避免服务端使用brotli导致aiohttp无法解压（未安装brotli库时会出现空响应）
        self.headers['accept-encoding'] = 'gzip, deflate'
        # 增量下载与数据库
        self.increase_cfg: Dict[str, Any] = self.config.get('increase', {}) or {}
        self.enable_database: bool = bool(self.config.get('database', True))
        self.db: Optional[DataBase] = DataBase() if self.enable_database else None
        
        # 保存路径
        self.save_path = Path(self.config.get('path', './Downloaded'))
        self.save_path.mkdir(parents=True, exist_ok=True)
        
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        if not os.path.exists(config_path):
            # 配置文件不存在时返回空配置
            print(f"警告: 配置文件 {config_path} 不存在，使用默认配置")
            return {}

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 简化配置兼容：links/link, output_dir/path, cookie/cookies
        if 'links' in config and 'link' not in config:
            config['link'] = config['links']
        if 'output_dir' in config and 'path' not in config:
            config['path'] = config['output_dir']
        if 'cookie' in config and 'cookies' not in config:
            config['cookies'] = config['cookie']
        if isinstance(config.get('cookies'), str) and config.get('cookies') == 'auto':
            config['auto_cookie'] = True

        # 允许无 link（通过命令行传入）
        # 如果两者都没有，后续会在运行时提示

        return config

    def _generate_mstoken(self) -> str:
        """生成msToken"""
        import random
        import string

        # msToken格式通常是一个随机字符串，长度约107个字符
        # 字符集包含大小写字母、数字和特殊字符
        charset = string.ascii_letters + string.digits + '-_='

        # 生成基础随机字符串
        base_length = random.randint(100, 110)
        mstoken = ''.join(random.choice(charset) for _ in range(base_length))

        logger.info(f"生成msToken: {mstoken[:20]}...")
        return mstoken

    def _generate_device_id(self) -> str:
        """生成设备ID"""
        import random

        # 设备ID通常是19位数字
        device_id = ''.join([str(random.randint(0, 9)) for _ in range(19)])
        logger.info(f"生成设备ID: {device_id}")
        return device_id
    
    def _build_cookie_string(self) -> str:
        """构建Cookie字符串"""
        if isinstance(self.cookies, str):
            return self.cookies
        elif isinstance(self.cookies, dict):
            return '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        elif isinstance(self.cookies, list):
            # 支持来自AutoCookieManager的cookies列表
            try:
                kv = {c.get('name'): c.get('value') for c in self.cookies if c.get('name') and c.get('value')}
                return '; '.join([f'{k}={v}' for k, v in kv.items()])
            except Exception:
                return ''
        return ''

    async def _initialize_cookies_and_headers(self):
        """初始化Cookie与请求头（支持多种获取方式）"""

        # 方式1: browser:chrome 模式（yt-dlp方式）
        if self.browser_cookie:
            try:
                console.print(f"[cyan]🔐 从{self.browser_cookie}浏览器提取Cookie（yt-dlp方式）...[/cyan]")
                from apiproxy.douyin.auth.browser_cookies import get_browser_cookies

                # 直接从浏览器数据库提取Cookie
                browser_cookies = get_browser_cookies(self.browser_cookie, '.douyin.com')

                if browser_cookies:
                    self.cookies = browser_cookies
                    cookie_str = self._build_cookie_string()
                    if cookie_str:
                        self.headers['Cookie'] = cookie_str
                        from apiproxy.douyin import douyin_headers
                        douyin_headers['Cookie'] = cookie_str

                        # 显示提取到的关键Cookie
                        if 'msToken' in browser_cookies:
                            console.print(f"[green]✅ 提取到msToken: {browser_cookies['msToken'][:30]}...[/green]")
                        if 'ttwid' in browser_cookies:
                            console.print(f"[green]✅ 提取到ttwid: {browser_cookies['ttwid'][:30]}...[/green]")
                        if 'sessionid' in browser_cookies:
                            console.print(f"[green]✅ 提取到sessionid（已登录）[/green]")

                        console.print(f"[green]✅ 从{self.browser_cookie}成功提取{len(browser_cookies)}个Cookie[/green]")
                        return

            except Exception as e:
                logger.error(f"从浏览器提取Cookie失败: {e}")
                console.print(f"[red]❌ 从{self.browser_cookie}提取Cookie失败: {e}[/red]")

        # 方式2: 配置为字符串 'auto'
        if isinstance(self.cookies, str) and self.cookies.strip().lower() == 'auto':
            self.cookies = None

        # 方式3: 已显式提供cookies
        cookie_str = self._build_cookie_string()
        if cookie_str:
            self.headers['Cookie'] = cookie_str
            from apiproxy.douyin import douyin_headers
            douyin_headers['Cookie'] = cookie_str
            return

        # 方式4: 自动获取Cookie（Playwright方式）
        if self.auto_cookie:
            try:
                console.print("[cyan]🔐 正在自动获取Cookie（Playwright方式）...[/cyan]")
                async with AutoCookieManager(cookie_file='cookies.pkl', headless=False) as cm:
                    cookies_list = await cm.get_cookies()
                    if cookies_list:
                        self.cookies = cookies_list
                        cookie_str = self._build_cookie_string()
                        if cookie_str:
                            self.headers['Cookie'] = cookie_str
                            from apiproxy.douyin import douyin_headers
                            douyin_headers['Cookie'] = cookie_str
                            console.print("[green]✅ Cookie获取成功[/green]")
                            return
                console.print("[yellow]⚠️ 自动获取Cookie失败或为空，继续尝试无Cookie模式[/yellow]")
            except Exception as e:
                logger.warning(f"自动获取Cookie失败: {e}")
                console.print("[yellow]⚠️ 自动获取Cookie失败，继续尝试无Cookie模式[/yellow]")

        # 未能获取Cookie则不设置，使用默认headers
    
    def detect_content_type(self, url: str) -> ContentType:
        """检测URL内容类型"""
        if '/user/' in url:
            return ContentType.USER
        elif '/video/' in url or 'v.douyin.com' in url:
            return ContentType.VIDEO
        elif '/note/' in url:
            return ContentType.IMAGE
        elif '/collection/' in url or '/mix/' in url:
            return ContentType.MIX
        elif '/music/' in url:
            return ContentType.MUSIC
        elif 'live.douyin.com' in url:
            return ContentType.LIVE
        else:
            return ContentType.VIDEO  # 默认当作视频
    
    async def resolve_short_url(self, url: str) -> str:
        """解析短链接"""
        if 'v.douyin.com' in url:
            try:
                # 使用更完整的请求头模拟浏览器
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"macOS"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1'
                }

                # 获取初次重定向
                session = requests.Session()
                response = session.get(url, headers=headers, allow_redirects=False, timeout=10)

                # 处理重定向链
                redirect_count = 0
                max_redirects = 5
                current_url = url

                while redirect_count < max_redirects:
                    if response.status_code in [301, 302, 303, 307, 308]:
                        location = response.headers.get('Location', '')
                        if location:
                            # 处理相对路径
                            if location.startswith('/'):
                                parsed = urlparse(current_url)
                                location = f"{parsed.scheme}://{parsed.netloc}{location}"
                            elif not location.startswith('http'):
                                parsed = urlparse(current_url)
                                location = f"{parsed.scheme}://{parsed.netloc}/{location}"

                            current_url = location
                            logger.debug(f"重定向 {redirect_count + 1}: {location}")

                            # 检查是否包含视频ID
                            if '/video/' in location or '/note/' in location or 'modal_id=' in location:
                                logger.info(f"解析短链接成功: {url} -> {location}")
                                return location

                            # 继续跟随重定向
                            response = session.get(location, headers=headers, allow_redirects=False, timeout=10)
                            redirect_count += 1
                        else:
                            break
                    else:
                        # 非重定向状态，检查最终URL
                        if '/video/' in current_url or '/note/' in current_url:
                            logger.info(f"解析短链接成功: {url} -> {current_url}")
                            return current_url
                        break

                # 如果上述方法失败，尝试直接访问并解析响应内容
                response = session.get(url, headers=headers, allow_redirects=True, timeout=10)
                final_url = response.url

                # 从响应内容中提取视频ID
                if response.text:
                    import re
                    # 尝试从页面中提取视频ID
                    video_id_match = re.search(r'/video/(\d+)', response.text)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        video_url = f"https://www.douyin.com/video/{video_id}"
                        logger.info(f"从页面内容提取视频ID: {url} -> {video_url}")
                        return video_url

                    # 尝试从 meta 标签中提取
                    canonical_match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', response.text)
                    if canonical_match:
                        canonical_url = canonical_match.group(1)
                        if '/video/' in canonical_url or '/note/' in canonical_url:
                            logger.info(f"从 canonical 标签提取: {url} -> {canonical_url}")
                            return canonical_url

                # 最后的备用：如果最终URL看起来有效
                if final_url and 'douyin.com' in final_url and final_url != 'https://www.douyin.com':
                    logger.info(f"解析短链接: {url} -> {final_url}")
                    return final_url

                logger.warning(f"解析短链接失败，返回原始URL: {url}")
                return url

            except Exception as e:
                logger.warning(f"解析短链接失败: {e}")
                import traceback
                traceback.print_exc()
        return url
    
    def extract_id_from_url(self, url: str, content_type: ContentType = None) -> Optional[str]:
        """从URL提取ID
        
        Args:
            url: 要解析的URL
            content_type: 内容类型（可选，用于指导提取）
        """
        # 如果已知是用户页面，直接提取用户ID
        if content_type == ContentType.USER or '/user/' in url:
            user_patterns = [
                r'/user/([\w-]+)',
                r'sec_uid=([\w-]+)'
            ]
            
            for pattern in user_patterns:
                match = re.search(pattern, url)
                if match:
                    user_id = match.group(1)
                    logger.info(f"提取到用户ID: {user_id}")
                    return user_id
        
        # 视频ID模式（优先）
        video_patterns = [
            r'/video/(\d+)',
            r'/note/(\d+)',
            r'modal_id=(\d+)',
            r'aweme_id=(\d+)',
            r'item_id=(\d+)'
        ]
        
        for pattern in video_patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.info(f"提取到视频ID: {video_id}")
                return video_id
        
        # 其他模式
        other_patterns = [
            r'/collection/(\d+)',
            r'/music/(\d+)'
        ]
        
        for pattern in other_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # 尝试从URL中提取数字ID
        number_match = re.search(r'(\d{15,20})', url)
        if number_match:
            video_id = number_match.group(1)
            logger.info(f"从URL提取到数字ID: {video_id}")
            return video_id
        
        logger.error(f"无法从URL提取ID: {url}")
        return None

    def _get_aweme_id_from_info(self, info: Dict) -> Optional[str]:
        """从 aweme 信息中提取 aweme_id"""
        try:
            if 'aweme_id' in info:
                return str(info.get('aweme_id'))
            # aweme_detail 结构
            return str(info.get('aweme', {}).get('aweme_id') or info.get('aweme_id'))
        except Exception:
            return None

    def _get_sec_uid_from_info(self, info: Dict) -> Optional[str]:
        """从 aweme 信息中提取作者 sec_uid"""
        try:
            return info.get('author', {}).get('sec_uid')
        except Exception:
            return None

    def _should_skip_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None) -> bool:
        """根据增量配置与数据库记录判断是否跳过下载"""
        if not self.db:
            return False
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id:
            return False

        try:
            if context == 'post' and self.increase_cfg.get('post', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_post(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'like' and self.increase_cfg.get('like', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_like(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'mix' and self.increase_cfg.get('mix', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                return bool(self.db.get_mix(sec, mid, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'music' and self.increase_cfg.get('music', False):
                mid = music_id or ''
                return bool(self.db.get_music(mid, int(aweme_id)) if aweme_id.isdigit() else None)
        except Exception:
            return False
        return False

    def _record_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None):
        """下载成功后写入数据库记录"""
        if not self.db:
            return
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id or not aweme_id.isdigit():
            return
        try:
            if context == 'post':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_post(sec, int(aweme_id), info)
            elif context == 'like':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_like(sec, int(aweme_id), info)
            elif context == 'mix':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                self.db.insert_mix(sec, mid, int(aweme_id), info)
            elif context == 'music':
                mid = music_id or ''
                self.db.insert_music(mid, int(aweme_id), info)
        except Exception:
            pass
    
    async def download_single_video(self, url: str, progress=None, task_id=None) -> bool:
        """下载单个视频/图文"""
        try:
            # 解析短链接
            url = await self.resolve_short_url(url)

            # 提取ID
            video_id = self.extract_id_from_url(url, ContentType.VIDEO)
            if not video_id:
                logger.error(f"无法从URL提取ID: {url}")
                return False

            # 如果没有提取到视频ID，尝试作为视频ID直接使用
            if not video_id and '/user/' not in url:
                # 可能短链接直接包含了视频ID
                video_id = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                logger.debug(f"尝试从短链接路径提取ID: {video_id}")

            if not video_id:
                logger.error(f"无法从URL提取视频ID: {url}")
                return False

            # 限速
            await self.rate_limiter.acquire()

            # 获取视频信息
            if progress and task_id is not None:
                progress.update(task_id, description="[yellow]获取视频信息...[/yellow]", completed=20)

            video_info = await self.retry_manager.execute_with_retry(
                self._fetch_video_info, video_id
            )

            if not video_info:
                logger.error(f"无法获取视频信息: {video_id}")
                self.stats.failed += 1
                return False

            # 下载视频文件
            if progress and task_id is not None:
                desc = video_info.get('desc', '无标题')[:30]
                media_type = '图文' if video_info.get('images') else '视频'
                progress.update(task_id, description=f"[cyan]下载{media_type}: {desc}[/cyan]", completed=40)

            success = await self._download_media_files(video_info, progress, task_id)

            if success:
                self.stats.success += 1
                logger.debug(f"下载成功: {url}")
            else:
                self.stats.failed += 1
                logger.error(f"下载失败: {url}")

            return success

        except Exception as e:
            logger.error(f"下载视频异常 {url}: {e}")
            self.stats.failed += 1
            return False
        finally:
            self.stats.total += 1
    
    async def _fetch_video_info(self, video_id: str) -> Optional[Dict]:
        """获取视频信息"""
        try:
            # 直接使用 DouYinCommand.py 中成功的 Douyin 类
            from apiproxy.douyin.douyin import Douyin
            
            # 创建 Douyin 实例
            dy = Douyin(database=False)
            
            # 设置我们的 cookies 到 douyin_headers
            if hasattr(self, 'cookies') and self.cookies:
                cookie_str = self._build_cookie_string()
                if cookie_str:
                    from apiproxy.douyin import douyin_headers
                    douyin_headers['Cookie'] = cookie_str
                    logger.info(f"设置 Cookie 到 Douyin 类: {cookie_str[:100]}...")
            
            try:
                # 使用现有的成功实现
                result = dy.getAwemeInfo(video_id)
                if result:
                    logger.info(f"Douyin 类成功获取视频信息: {result.get('desc', '')[:30]}")
                    return result
                else:
                    logger.error("Douyin 类返回空结果")
                    
            except Exception as e:
                logger.error(f"Douyin 类获取视频信息失败: {e}")
                
        except Exception as e:
            logger.error(f"导入或使用 Douyin 类失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 如果 Douyin 类失败，尝试增强的备用接口
        try:
            # 尝试使用带X-Bogus的官方API
            params = self._build_detail_params(video_id)

            # 生成X-Bogus签名
            try:
                x_bogus = get_x_bogus(params, douyin_headers.get('User-Agent'))
                api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?{params}&X-Bogus={x_bogus}"
                logger.info(f"尝试使用X-Bogus签名的API: {api_url[:100]}...")
            except Exception as e:
                logger.warning(f"生成X-Bogus失败: {e}, 使用无签名备用接口")
                api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"

            # 设置更完整的请求头
            headers = {**douyin_headers}
            headers.update({
                'Referer': 'https://www.douyin.com/',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            })

            # 添加Cookie和msToken
            if hasattr(self, 'cookies') and self.cookies:
                cookie_str = self._build_cookie_string()
                if cookie_str:
                    if 'msToken=' not in cookie_str:
                        cookie_str += f'; msToken={self.mstoken}'
                    headers['Cookie'] = cookie_str
            else:
                headers['Cookie'] = f'msToken={self.mstoken}'

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=15) as response:
                    logger.info(f"备用接口响应状态: {response.status}")
                    if response.status != 200:
                        logger.error(f"备用接口请求失败，状态码: {response.status}")
                        return None

                    text = await response.text()
                    logger.info(f"备用接口响应内容长度: {len(text)}")

                    if not text:
                        logger.error("备用接口响应为空")
                        return None

                    try:
                        data = json.loads(text)

                        # 处理不同的响应格式
                        if 'aweme_detail' in data:
                            aweme_detail = data['aweme_detail']
                            logger.info("备用接口成功获取视频信息（aweme_detail格式）")
                            return aweme_detail
                        elif 'item_list' in data:
                            item_list = data.get('item_list', [])
                            if item_list:
                                aweme_detail = item_list[0]
                                logger.info("备用接口成功获取视频信息（item_list格式）")
                                return aweme_detail
                        else:
                            logger.error(f"备用接口返回未知格式: {list(data.keys())}")

                    except json.JSONDecodeError as e:
                        logger.error(f"备用接口JSON解析失败: {e}")
                        logger.error(f"原始响应内容: {text[:500]}...")
                        return None

        except Exception as e:
            logger.error(f"备用接口获取视频信息失败: {e}")

        # 最后的降级策略：HTML解析
        return await self._try_html_parse(video_id)
    
    def _build_detail_params(self, aweme_id: str) -> str:
        """构建详情API参数"""
        # 使用增强的参数格式，包含必要的设备指纹信息
        params = [
            f'aweme_id={aweme_id}',
            'device_platform=webapp',
            'aid=6383',
            'channel=channel_pc_web',
            'pc_client_type=1',
            'version_code=170400',
            'version_name=17.4.0',
            'cookie_enabled=true',
            'screen_width=1920',
            'screen_height=1080',
            'browser_language=zh-CN',
            'browser_platform=MacIntel',
            'browser_name=Chrome',
            'browser_version=122.0.0.0',
            'browser_online=true',
            'engine_name=Blink',
            'engine_version=122.0.0.0',
            'os_name=Mac',
            'os_version=10.15.7',
            'cpu_core_num=8',
            'device_memory=8',
            'platform=PC',
            'downlink=10',
            'effective_type=4g',
            'round_trip_time=50',
            f'msToken={self.mstoken}',
            f'device_id={self.device_id}',
        ]
        return '&'.join(params)

    async def _try_html_parse(self, video_id: str) -> Optional[Dict]:
        """HTML解析降级策略 - 当API都失败时尝试从网页解析"""
        try:
            logger.info("尝试HTML解析策略获取视频信息")

            # 构建网页URL
            share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"

            # 设置模拟浏览器的请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Upgrade-Insecure-Requests': '1'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(share_url, headers=headers, timeout=20) as response:
                    if response.status != 200:
                        logger.warning(f"HTML页面请求失败，状态码: {response.status}")
                        return None

                    html = await response.text()
                    if not html:
                        logger.warning("HTML页面内容为空")
                        return None

                    # 解析HTML内容
                    return self._parse_html_content(html, video_id)

        except Exception as e:
            logger.error(f"HTML解析策略失败: {e}")
            return None

    def _parse_html_content(self, html: str, video_id: str) -> Optional[Dict]:
        """解析HTML内容提取视频信息"""
        import re
        import urllib.parse

        try:
            # 方法1：从RENDER_DATA脚本标签中提取
            render_data_pattern = r'<script id="RENDER_DATA" type="application/json">(.*?)</script>'
            match = re.search(render_data_pattern, html, re.DOTALL)

            if match:
                try:
                    # URL解码
                    data_str = urllib.parse.unquote(match.group(1))
                    data = json.loads(data_str)

                    # 遍历数据查找视频信息
                    for key, value in data.items():
                        if isinstance(value, dict):
                            # 查找包含aweme信息的节点
                            if 'aweme' in str(value).lower():
                                aweme_data = self._extract_aweme_from_render_data(value)
                                if aweme_data:
                                    logger.info("HTML解析成功（RENDER_DATA方式）")
                                    return aweme_data

                except Exception as e:
                    logger.debug(f"解析RENDER_DATA失败: {e}")

            # 方法2：从其他script标签中提取视频信息
            script_patterns = [
                r'window\._SSR_HYDRATED_DATA\s*=\s*({.*?});',
                r'window\.INITIAL_STATE\s*=\s*({.*?});',
                r'__INITIAL_STATE__\s*=\s*({.*?});',
                r'window\.__NUXT__\s*=\s*({.*?});'
            ]

            for pattern in script_patterns:
                matches = re.finditer(pattern, html, re.DOTALL)
                for match in matches:
                    try:
                        data_str = match.group(1)
                        data = json.loads(data_str)
                        aweme_data = self._extract_aweme_from_script_data(data, video_id)
                        if aweme_data:
                            logger.info(f"HTML解析成功（script方式）")
                            return aweme_data
                    except Exception as e:
                        logger.debug(f"解析script数据失败: {e}")

            # 方法3：提取meta标签中的信息
            meta_info = self._extract_meta_info(html)
            if meta_info:
                # 构建基础的aweme结构
                basic_aweme = {
                    'aweme_id': video_id,
                    'desc': meta_info.get('description', ''),
                    'create_time': int(time.time()),  # 使用当前时间戳作为创建时间
                    'author': {
                        'nickname': meta_info.get('author', 'unknown'),
                        'unique_id': meta_info.get('author', 'unknown'),
                        'sec_uid': ''
                    },
                    'statistics': {
                        'digg_count': 0,
                        'comment_count': 0,
                        'share_count': 0,
                        'play_count': 0
                    },
                    'video': {
                        'play_addr': {'url_list': []},
                        'download_addr': {'url_list': []},
                        'cover': {'url_list': [meta_info.get('cover', '')]}
                    },
                    'music': {
                        'title': '',
                        'play_url': {'url_list': []}
                    }
                }
                logger.info("HTML解析成功（meta标签方式，基础信息）")
                return basic_aweme

            logger.warning("HTML解析未能提取到有效的视频信息")
            return None

        except Exception as e:
            logger.error(f"HTML内容解析失败: {e}")
            return None

    def _extract_aweme_from_render_data(self, data: Dict) -> Optional[Dict]:
        """从RENDER_DATA中提取aweme信息"""
        try:
            # 递归搜索aweme相关数据
            if isinstance(data, dict):
                for key, value in data.items():
                    if 'aweme' in key.lower() and isinstance(value, dict):
                        if 'aweme_id' in value or 'video' in value:
                            return value
                    elif isinstance(value, (dict, list)):
                        result = self._extract_aweme_from_render_data(value)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = self._extract_aweme_from_render_data(item)
                        if result:
                            return result
        except Exception:
            pass
        return None

    def _extract_aweme_from_script_data(self, data: Dict, video_id: str) -> Optional[Dict]:
        """从script数据中提取aweme信息"""
        try:
            # 递归搜索包含video_id的aweme数据
            if isinstance(data, dict):
                if data.get('aweme_id') == video_id:
                    return data
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        result = self._extract_aweme_from_script_data(value, video_id)
                        if result:
                            return result
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        result = self._extract_aweme_from_script_data(item, video_id)
                        if result:
                            return result
        except Exception:
            pass
        return None

    def _extract_meta_info(self, html: str) -> Dict:
        """从meta标签中提取基础信息"""
        import re

        meta_info = {}

        # 提取标题/描述
        title_pattern = r'<title[^>]*>(.*?)</title>'
        title_match = re.search(title_pattern, html, re.IGNORECASE | re.DOTALL)
        if title_match:
            meta_info['description'] = title_match.group(1).strip()

        # 提取meta描述
        desc_pattern = r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']'
        desc_match = re.search(desc_pattern, html, re.IGNORECASE)
        if desc_match:
            meta_info['description'] = desc_match.group(1).strip()

        # 提取作者信息
        author_patterns = [
            r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']*)["\']',
            r'@([^@\s]+)',  # 从标题中提取@用户名
        ]

        for pattern in author_patterns:
            author_match = re.search(pattern, html, re.IGNORECASE)
            if author_match:
                meta_info['author'] = author_match.group(1).strip()
                break

        # 提取封面图
        cover_patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']*)["\']'
        ]

        for pattern in cover_patterns:
            cover_match = re.search(pattern, html, re.IGNORECASE)
            if cover_match:
                meta_info['cover'] = cover_match.group(1).strip()
                break

        return meta_info

    def _enhance_video_url(self, url: str) -> str:
        """增强视频URL，尝试获取更高质量的版本"""
        if not url:
            return url

        # 替换为无水印版本
        enhanced_url = url.replace('playwm', 'play')

        # 尝试获取更高质量
        quality_replacements = [
            ('720p', '1080p'),
            ('480p', '720p'),
            ('360p', '480p'),
        ]

        for old_quality, new_quality in quality_replacements:
            if old_quality in enhanced_url:
                enhanced_url = enhanced_url.replace(old_quality, new_quality)
                break

        logger.debug(f"URL增强: {url} -> {enhanced_url}")
        return enhanced_url

    def _get_fallback_user_agent(self) -> str:
        """获取备用User-Agent"""
        user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
        ]
        import random
        return random.choice(user_agents)

    async def _validate_video_info(self, video_info: Dict) -> bool:
        """验证视频信息的完整性"""
        if not video_info:
            return False

        # 基本字段检查
        required_fields = ['aweme_id']
        for field in required_fields:
            if field not in video_info:
                logger.warning(f"视频信息缺少必要字段: {field}")
                return False

        # 检查是否有可下载的内容
        has_video = bool(video_info.get('video', {}).get('play_addr', {}).get('url_list'))
        has_images = bool(video_info.get('images'))

        if not has_video and not has_images:
            logger.warning("视频信息中没有可下载的媒体内容")
            return False

        return True

    async def _get_alternative_endpoints(self, aweme_id: str) -> List[str]:
        """获取备用API端点列表"""
        endpoints = [
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}",
            f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}",
            f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}",
            f"https://aweme.snssdk.com/aweme/v1/aweme/detail/?aweme_id={aweme_id}",
        ]

        # 为每个端点添加完整参数
        enhanced_endpoints = []
        for endpoint in endpoints:
            if '?' in endpoint:
                base_url, existing_params = endpoint.split('?', 1)
                full_params = existing_params + '&' + self._build_detail_params(aweme_id).replace(f'aweme_id={aweme_id}&', '')
            else:
                full_params = self._build_detail_params(aweme_id)
                base_url = endpoint

            enhanced_endpoints.append(f"{base_url}?{full_params}")

        return enhanced_endpoints

    async def _download_media_files(self, video_info: Dict, progress=None, task_id=None) -> bool:
        """下载媒体文件"""
        try:
            # 判断类型
            is_image = bool(video_info.get('images'))

            # 构建保存路径
            author_name = video_info.get('author', {}).get('nickname', 'unknown')
            desc = video_info.get('desc', '')[:50].replace('/', '_')
            # 兼容 create_time 为时间戳或格式化字符串
            raw_create_time = video_info.get('create_time')
            dt_obj = None
            if isinstance(raw_create_time, (int, float)):
                dt_obj = datetime.fromtimestamp(raw_create_time)
            elif isinstance(raw_create_time, str) and raw_create_time:
                for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                    try:
                        dt_obj = datetime.strptime(raw_create_time, fmt)
                        break
                    except Exception:
                        pass
            if dt_obj is None:
                dt_obj = datetime.fromtimestamp(time.time())
            create_time = dt_obj.strftime('%Y-%m-%d_%H-%M-%S')

            folder_name = f"{create_time}_{desc}" if desc else create_time
            save_dir = self.save_path / author_name / folder_name
            save_dir.mkdir(parents=True, exist_ok=True)

            success = True

            if is_image:
                # 下载图文（无水印）
                images = video_info.get('images', [])
                total_images = len(images)

                for i, img in enumerate(images, 1):
                    img_url = self._get_best_quality_url(img.get('url_list', []))
                    if img_url:
                        file_path = save_dir / f"image_{i}.jpg"
                        # 更新进度描述
                        if progress and task_id is not None:
                            progress.update(
                                task_id,
                                description=f"[cyan]下载图片 {i}/{total_images}: {file_path.name}[/cyan]",
                                completed=(i - 1) * 100 / total_images
                            )

                        if await self._download_file_with_progress(img_url, file_path, progress, task_id, i, total_images):
                            logger.debug(f"下载图片 {i}/{total_images}: {file_path.name}")
                        else:
                            success = False

                # 更新完成状态
                if progress and task_id is not None:
                    progress.update(task_id, completed=100, description=f"[green]✓ 下载完成 {total_images} 张图片[/green]")
            else:
                # 下载视频（无水印）
                video_url = self._get_no_watermark_url(video_info)
                if video_url:
                    file_path = save_dir / f"{folder_name}.mp4"
                    if progress and task_id is not None:
                        progress.update(task_id, description=f"[cyan]下载视频: {file_path.name}[/cyan]")

                    if await self._download_file_with_progress(video_url, file_path, progress, task_id):
                        logger.debug(f"下载视频: {file_path.name}")
                    else:
                        success = False

                # 下载音频
                if self.config.get('music', True):
                    music_url = self._get_music_url(video_info)
                    if music_url:
                        file_path = save_dir / f"{folder_name}_music.mp3"
                        if progress and task_id is not None:
                            progress.update(task_id, description=f"[dim]下载音频...[/dim]")
                        await self._download_file(music_url, file_path)

                # 更新完成状态
                if progress and task_id is not None:
                    progress.update(task_id, completed=100, description=f"[green]✓ 下载完成[/green]")

            # 下载封面
            if self.config.get('cover', True):
                cover_url = self._get_cover_url(video_info)
                if cover_url:
                    file_path = save_dir / f"{folder_name}_cover.jpg"
                    await self._download_file(cover_url, file_path)

            # 保存JSON数据
            if self.config.get('json', True):
                json_path = save_dir / f"{folder_name}_data.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)

            return success

        except Exception as e:
            logger.error(f"下载媒体文件失败: {e}")
            return False
    
    def _get_no_watermark_url(self, video_info: Dict) -> Optional[str]:
        """获取无水印视频URL"""
        try:
            # 优先使用play_addr_h264
            play_addr = video_info.get('video', {}).get('play_addr_h264') or \
                       video_info.get('video', {}).get('play_addr')

            if play_addr:
                url_list = play_addr.get('url_list', [])
                if url_list:
                    # 使用增强的URL处理
                    url = self._enhance_video_url(url_list[0])
                    return url

            # 备用：download_addr
            download_addr = video_info.get('video', {}).get('download_addr')
            if download_addr:
                url_list = download_addr.get('url_list', [])
                if url_list:
                    return self._enhance_video_url(url_list[0])

            # 再次备用：bit_rate数组中的URL
            bit_rate_list = video_info.get('video', {}).get('bit_rate', [])
            for bit_rate in bit_rate_list:
                play_addr = bit_rate.get('play_addr', {})
                url_list = play_addr.get('url_list', [])
                if url_list:
                    return self._enhance_video_url(url_list[0])

        except Exception as e:
            logger.error(f"获取无水印URL失败: {e}")

        return None
    
    def _get_best_quality_url(self, url_list: List[str]) -> Optional[str]:
        """获取最高质量的URL"""
        if not url_list:
            return None
        
        # 优先选择包含特定关键词的URL
        for keyword in ['1080', 'origin', 'high']:
            for url in url_list:
                if keyword in url:
                    return url
        
        # 返回第一个
        return url_list[0]
    
    def _get_music_url(self, video_info: Dict) -> Optional[str]:
        """获取音乐URL"""
        try:
            music = video_info.get('music', {})
            play_url = music.get('play_url', {})
            url_list = play_url.get('url_list', [])
            return url_list[0] if url_list else None
        except:
            return None
    
    def _get_cover_url(self, video_info: Dict) -> Optional[str]:
        """获取封面URL"""
        try:
            cover = video_info.get('video', {}).get('cover', {})
            url_list = cover.get('url_list', [])
            return self._get_best_quality_url(url_list)
        except:
            return None
    
    async def _download_file(self, url: str, save_path: Path) -> bool:
        """下载文件"""
        try:
            if save_path.exists():
                logger.debug(f"文件已存在，跳过: {save_path.name}")
                return True

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        return True
                    else:
                        logger.error(f"下载失败，状态码: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"下载文件失败 {url}: {e}")
            return False

    async def _download_file_with_progress(self, url: str, save_path: Path, progress=None, task_id=None, current=1, total=1) -> bool:
        """带进度显示的文件下载"""
        try:
            if save_path.exists():
                logger.debug(f"文件已存在，跳过: {save_path.name}")
                return True

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        chunk_size = 8192
                        downloaded = 0

                        with open(save_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)

                                # 更新进度
                                if progress and task_id is not None and total_size > 0:
                                    if total > 1:
                                        # 多文件情况下的进度计算
                                        file_progress = downloaded / total_size
                                        overall_progress = ((current - 1) + file_progress) * 100 / total
                                        progress.update(task_id, completed=overall_progress)
                                    else:
                                        # 单文件进度
                                        progress.update(task_id, completed=downloaded * 100 / total_size)

                        return True
                    else:
                        logger.error(f"下载失败，状态码: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"下载文件失败: {e}")
            return False
    
    async def download_user_page(self, url: str) -> bool:
        """下载用户主页内容"""
        try:
            # 提取用户ID
            user_id = self.extract_id_from_url(url, ContentType.USER)
            if not user_id:
                logger.error(f"无法从URL提取用户ID: {url}")
                return False
            
            console.print(f"\n[cyan]正在获取用户 {user_id} 的作品列表...[/cyan]")
            
            # 根据配置下载不同类型的内容
            mode = self.config.get('mode', ['post'])
            if isinstance(mode, str):
                mode = [mode]
            
            # 增加总任务数统计
            total_posts = 0
            if 'post' in mode:
                total_posts += self.config.get('number', {}).get('post', 0) or 1
            if 'like' in mode:
                total_posts += self.config.get('number', {}).get('like', 0) or 1
            if 'mix' in mode:
                total_posts += self.config.get('number', {}).get('allmix', 0) or 1
            
            self.stats.total += total_posts
            
            for m in mode:
                if m == 'post':
                    await self._download_user_posts(user_id)
                elif m == 'like':
                    await self._download_user_likes(user_id)
                elif m == 'mix':
                    await self._download_user_mixes(user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"下载用户主页失败: {e}")
            return False
    
    async def _download_user_posts(self, user_id: str):
        """下载用户发布的作品"""
        max_count = self.config.get('number', {}).get('post', 0)
        cursor = 0
        downloaded = 0
        skipped = 0

        console.print(f"\n[bold cyan]📥 开始下载用户发布的作品[/bold cyan]")
        console.print(f"[dim]用户ID: {user_id}[/dim]")
        if max_count > 0:
            console.print(f"[dim]限制数量: {max_count}[/dim]")

        # 创建独立的Progress实例，避免冲突
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[dim]•[/dim]"),
            TimeRemainingColumn(),
            console=console,
            refresh_per_second=2,
            transient=True  # 完成后清除
        )

        with progress:

            # 主任务进度条
            main_task = progress.add_task(
                "[yellow]获取作品列表...[/yellow]",
                total=None
            )

            while True:
                # 限速
                await self.rate_limiter.acquire()

                # 获取作品列表
                posts_data = await self._fetch_user_posts(user_id, cursor)
                if not posts_data:
                    break

                aweme_list = posts_data.get('aweme_list', [])
                if not aweme_list:
                    break

                # 更新主任务
                progress.update(
                    main_task,
                    description=f"[cyan]处理作品批次 (已下载: {downloaded}, 已跳过: {skipped})[/cyan]"
                )

                # 下载作品
                for aweme in aweme_list:
                    if max_count > 0 and downloaded >= max_count:
                        console.print(f"\n[yellow]⚠️ 已达到下载数量限制: {max_count}[/yellow]")
                        return

                    # 时间过滤
                    if not self._check_time_filter(aweme):
                        skipped += 1
                        continue

                    # 增量判断
                    if self._should_skip_increment('post', aweme, sec_uid=user_id):
                        skipped += 1
                        continue

                    # 获取作品信息
                    desc = aweme.get('desc', '无标题')[:30]
                    aweme_type = '图文' if aweme.get('images') else '视频'

                    # 创建下载任务
                    task_id = progress.add_task(
                        f"[cyan]{aweme_type}[/cyan] {desc}",
                        total=100
                    )

                    # 下载
                    success = await self._download_media_files(aweme, progress, task_id)

                    if success:
                        downloaded += 1
                        self.stats.success += 1
                        self._record_increment('post', aweme, sec_uid=user_id)
                    else:
                        self.stats.failed += 1
                        progress.update(task_id, description=f"[red]✗ 失败[/red] {desc}")

                    # 移除完成的任务（保持界面整洁）
                    progress.remove_task(task_id)

                # 检查是否有更多
                if not posts_data.get('has_more'):
                    break

                cursor = posts_data.get('max_cursor', 0)

            # 完成主任务
            progress.update(main_task, description="[green]✓ 作品下载完成[/green]")
            progress.remove_task(main_task)

        # 显示统计
        console.print(f"\n[bold green]✅ 用户作品下载完成[/bold green]")
        console.print(f"   下载: {downloaded} | 跳过: {skipped} | 失败: {self.stats.failed}")
    
    async def _fetch_user_posts(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户作品列表"""
        try:
            # 直接使用 Douyin 类的 getUserInfo 方法，就像 DouYinCommand.py 那样
            from apiproxy.douyin.douyin import Douyin
            
            # 创建 Douyin 实例
            dy = Douyin(database=False)
            
            # 获取用户作品列表
            result = dy.getUserInfo(
                user_id, 
                "post", 
                35, 
                0,  # 不限制数量
                False,  # 不启用增量
                "",  # start_time
                ""   # end_time
            )
            
            if result:
                logger.info(f"Douyin 类成功获取用户作品列表，共 {len(result)} 个作品")
                # 转换为期望的格式
                return {
                    'status_code': 0,
                    'aweme_list': result,
                    'max_cursor': cursor,
                    'has_more': False
                }
            else:
                logger.error("Douyin 类返回空结果")
                return None
                
        except Exception as e:
            logger.error(f"获取用户作品列表失败: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    async def _download_user_likes(self, user_id: str):
        """下载用户喜欢的作品"""
        max_count = 0
        try:
            max_count = int(self.config.get('number', {}).get('like', 0))
        except Exception:
            max_count = 0
        cursor = 0
        downloaded = 0
        skipped = 0

        console.print(f"\n[bold cyan]❤️ 开始下载用户喜欢的作品[/bold cyan]")
        console.print(f"[dim]用户ID: {user_id}[/dim]")
        if max_count > 0:
            console.print(f"[dim]限制数量: {max_count}[/dim]")

        # 创建独立的Progress实例
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[dim]•[/dim]"),
            TimeRemainingColumn(),
            console=console,
            refresh_per_second=2,
            transient=True
        )

        with progress:

            # 主任务进度条
            main_task = progress.add_task(
                "[yellow]获取喜欢列表...[/yellow]",
                total=None
            )

            while True:
                # 限速
                await self.rate_limiter.acquire()

                # 获取喜欢列表
                likes_data = await self._fetch_user_likes(user_id, cursor)
                if not likes_data:
                    break

                aweme_list = likes_data.get('aweme_list', [])
                if not aweme_list:
                    break

                # 更新主任务
                progress.update(
                    main_task,
                    description=f"[cyan]处理喜欢批次 (已下载: {downloaded}, 已跳过: {skipped})[/cyan]"
                )

                # 下载作品
                for aweme in aweme_list:
                    if max_count > 0 and downloaded >= max_count:
                        console.print(f"\n[yellow]⚠️ 已达到下载数量限制: {max_count}[/yellow]")
                        return

                    if not self._check_time_filter(aweme):
                        skipped += 1
                        continue

                    # 增量判断
                    if self._should_skip_increment('like', aweme, sec_uid=user_id):
                        skipped += 1
                        continue

                    # 获取作品信息
                    desc = aweme.get('desc', '无标题')[:30]
                    aweme_type = '图文' if aweme.get('images') else '视频'

                    # 创建下载任务
                    task_id = progress.add_task(
                        f"[magenta]{aweme_type}[/magenta] {desc}",
                        total=100
                    )

                    success = await self._download_media_files(aweme, progress, task_id)

                    if success:
                        downloaded += 1
                        self.stats.success += 1
                        self._record_increment('like', aweme, sec_uid=user_id)
                    else:
                        self.stats.failed += 1
                        progress.update(task_id, description=f"[red]✗ 失败[/red] {desc}")

                    # 移除完成的任务
                    progress.remove_task(task_id)

                # 翻页
                if not likes_data.get('has_more'):
                    break
                cursor = likes_data.get('max_cursor', 0)

            # 完成主任务
            progress.update(main_task, description="[green]✓ 喜欢下载完成[/green]")
            progress.remove_task(main_task)

        # 显示统计
        console.print(f"\n[bold green]✅ 喜欢作品下载完成[/bold green]")
        console.print(f"   下载: {downloaded} | 跳过: {skipped} | 失败: {self.stats.failed}")

    async def _fetch_user_likes(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户喜欢的作品列表"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'max_cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true',
                'engine_name=Blink',
                'engine_version=122.0.0.0',
                'os_name=Mac',
                'os_version=10.15.7',
                'cpu_core_num=8',
                'device_memory=8',
                'platform=PC',
                'downlink=10',
                'effective_type=4g',
                'round_trip_time=50',
                f'msToken={self.mstoken}',
                f'device_id={self.device_id}',
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_FAVORITE_A

            # 使用增强的签名生成
            try:
                x_bogus = get_x_bogus(params, self.headers.get('User-Agent'))
                full_url = f"{api_url}{params}&X-Bogus={x_bogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试原有方法")
                try:
                    xbogus = self.utils.getXbogus(params)
                    full_url = f"{api_url}{params}&X-Bogus={xbogus}"
                except Exception as e2:
                    logger.warning(f"原有X-Bogus方法也失败: {e2}, 使用无签名")
                    full_url = f"{api_url}{params}"

            logger.info(f"请求用户喜欢列表: {full_url[:100]}...")

            # 确保headers包含msToken
            headers = {**self.headers}
            if 'Cookie' in headers:
                if 'msToken=' not in headers['Cookie']:
                    headers['Cookie'] += f'; msToken={self.mstoken}'
            else:
                headers['Cookie'] = f'msToken={self.mstoken}'

            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None

                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None

                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API返回错误: {data.get('status_msg', '未知错误')}")
                        return None
        except Exception as e:
            logger.error(f"获取用户喜欢列表失败: {e}")
        return None

    async def _download_user_mixes(self, user_id: str):
        """下载用户的所有合集（按配置可限制数量）"""
        max_allmix = 0
        try:
            # 兼容旧键名 allmix 或 mix
            number_cfg = self.config.get('number', {}) or {}
            max_allmix = int(number_cfg.get('allmix', number_cfg.get('mix', 0)) or 0)
        except Exception:
            max_allmix = 0

        cursor = 0
        fetched = 0

        console.print(f"\n[green]开始获取用户合集列表...[/green]")
        while True:
            await self.rate_limiter.acquire()
            mix_list_data = await self._fetch_user_mix_list(user_id, cursor)
            if not mix_list_data:
                break

            mix_infos = mix_list_data.get('mix_infos') or []
            if not mix_infos:
                break

            for mix in mix_infos:
                if max_allmix > 0 and fetched >= max_allmix:
                    console.print(f"[yellow]已达到合集数量限制: {max_allmix}[/yellow]")
                    return
                mix_id = mix.get('mix_id')
                mix_name = mix.get('mix_name', '')
                console.print(f"[cyan]下载合集[/cyan]: {mix_name} ({mix_id})")
                await self._download_mix_by_id(mix_id)
                fetched += 1

            if not mix_list_data.get('has_more'):
                break
            cursor = mix_list_data.get('cursor', 0)

        console.print(f"[green]✅ 用户合集下载完成，共处理 {fetched} 个[/green]")

    async def _fetch_user_mix_list(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取用户合集列表"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true',
                'engine_name=Blink',
                'engine_version=122.0.0.0',
                'os_name=Mac',
                'os_version=10.15.7',
                'cpu_core_num=8',
                'device_memory=8',
                'platform=PC',
                'downlink=10',
                'effective_type=4g',
                'round_trip_time=50',
                f'msToken={self.mstoken}',
                f'device_id={self.device_id}',
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX_LIST
            try:
                x_bogus = get_x_bogus(params, self.headers.get('User-Agent'))
                full_url = f"{api_url}{params}&X-Bogus={x_bogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试原有方法")
                try:
                    xbogus = self.utils.getXbogus(params)
                    full_url = f"{api_url}{params}&X-Bogus={xbogus}"
                except Exception as e2:
                    logger.warning(f"原有X-Bogus方法也失败: {e2}, 使用无签名")
                    full_url = f"{api_url}{params}"

            logger.info(f"请求用户合集列表: {full_url[:100]}...")

            # 确保headers包含msToken
            headers = {**self.headers}
            if 'Cookie' in headers:
                if 'msToken=' not in headers['Cookie']:
                    headers['Cookie'] += f'; msToken={self.mstoken}'
            else:
                headers['Cookie'] = f'msToken={self.mstoken}'

            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API返回错误: {data.get('status_msg', '未知错误')}")
                        return None
        except Exception as e:
            logger.error(f"获取用户合集列表失败: {e}")
        return None

    async def download_mix(self, url: str) -> bool:
        """根据合集链接下载合集内所有作品"""
        try:
            mix_id = None
            for pattern in [r'/collection/(\d+)', r'/mix/detail/(\d+)']:
                m = re.search(pattern, url)
                if m:
                    mix_id = m.group(1)
                    break
            if not mix_id:
                logger.error(f"无法从合集链接提取ID: {url}")
                return False
            await self._download_mix_by_id(mix_id)
            return True
        except Exception as e:
            logger.error(f"下载合集失败: {e}")
            return False

    async def _download_mix_by_id(self, mix_id: str):
        """按合集ID下载全部作品"""
        cursor = 0
        downloaded = 0

        console.print(f"\n[green]开始下载合集 {mix_id} ...[/green]")

        while True:
            await self.rate_limiter.acquire()
            data = await self._fetch_mix_awemes(mix_id, cursor)
            if not data:
                break

            aweme_list = data.get('aweme_list') or []
            if not aweme_list:
                break

            for aweme in aweme_list:
                success = await self._download_media_files(aweme)
                if success:
                    downloaded += 1

            if not data.get('has_more'):
                break
            cursor = data.get('cursor', 0)

        console.print(f"[green]✅ 合集下载完成，共下载 {downloaded} 个[/green]")

    async def _fetch_mix_awemes(self, mix_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取合集下作品列表"""
        try:
            params_list = [
                f'mix_id={mix_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true',
                'engine_name=Blink',
                'engine_version=122.0.0.0',
                'os_name=Mac',
                'os_version=10.15.7',
                'cpu_core_num=8',
                'device_memory=8',
                'platform=PC',
                'downlink=10',
                'effective_type=4g',
                'round_trip_time=50',
                f'msToken={self.mstoken}',
                f'device_id={self.device_id}',
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX
            try:
                x_bogus = get_x_bogus(params, self.headers.get('User-Agent'))
                full_url = f"{api_url}{params}&X-Bogus={x_bogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试原有方法")
                try:
                    xbogus = self.utils.getXbogus(params)
                    full_url = f"{api_url}{params}&X-Bogus={xbogus}"
                except Exception as e2:
                    logger.warning(f"原有X-Bogus方法也失败: {e2}, 使用无签名")
                    full_url = f"{api_url}{params}"

            logger.info(f"请求合集作品列表: {full_url[:100]}...")

            # 确保headers包含msToken
            headers = {**self.headers}
            if 'Cookie' in headers:
                if 'msToken=' not in headers['Cookie']:
                    headers['Cookie'] += f'; msToken={self.mstoken}'
            else:
                headers['Cookie'] = f'msToken={self.mstoken}'

            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    # USER_MIX 返回没有统一的 status_code，这里直接返回
                    return data
        except Exception as e:
            logger.error(f"获取合集作品失败: {e}")
        return None

    async def download_music(self, url: str) -> bool:
        """根据音乐页链接下载音乐下的所有作品（支持增量）"""
        try:
            # 提取 music_id
            music_id = None
            m = re.search(r'/music/(\d+)', url)
            if m:
                music_id = m.group(1)
            if not music_id:
                logger.error(f"无法从音乐链接提取ID: {url}")
                return False

            cursor = 0
            downloaded = 0
            limit_num = 0
            try:
                limit_num = int((self.config.get('number', {}) or {}).get('music', 0))
            except Exception:
                limit_num = 0

            console.print(f"\n[green]开始下载音乐 {music_id} 下的作品...[/green]")

            while True:
                await self.rate_limiter.acquire()
                data = await self._fetch_music_awemes(music_id, cursor)
                if not data:
                    break
                aweme_list = data.get('aweme_list') or []
                if not aweme_list:
                    break

                for aweme in aweme_list:
                    if limit_num > 0 and downloaded >= limit_num:
                        console.print(f"[yellow]已达到音乐下载数量限制: {limit_num}[/yellow]")
                        return True
                    if self._should_skip_increment('music', aweme, music_id=music_id):
                        continue
                    success = await self._download_media_files(aweme)
                    if success:
                        downloaded += 1
                        self._record_increment('music', aweme, music_id=music_id)

                if not data.get('has_more'):
                    break
                cursor = data.get('cursor', 0)

            console.print(f"[green]✅ 音乐作品下载完成，共下载 {downloaded} 个[/green]")
            return True
        except Exception as e:
            logger.error(f"下载音乐页失败: {e}")
            return False

    async def _fetch_music_awemes(self, music_id: str, cursor: int = 0) -> Optional[Dict]:
        """获取音乐下作品列表"""
        try:
            params_list = [
                f'music_id={music_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.MUSIC
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"获取X-Bogus失败: {e}, 尝试不带X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"请求音乐作品列表: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("响应内容为空")
                        return None
                    data = json.loads(text)
                    return data
        except Exception as e:
            logger.error(f"获取音乐作品失败: {e}")
        return None
    
    def _check_time_filter(self, aweme: Dict) -> bool:
        """检查时间过滤"""
        start_time = self.config.get('start_time')
        end_time = self.config.get('end_time')
        
        if not start_time and not end_time:
            return True
        
        raw_create_time = aweme.get('create_time')
        if not raw_create_time:
            return True
        
        create_date = None
        if isinstance(raw_create_time, (int, float)):
            try:
                create_date = datetime.fromtimestamp(raw_create_time)
            except Exception:
                create_date = None
        elif isinstance(raw_create_time, str):
            for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    create_date = datetime.strptime(raw_create_time, fmt)
                    break
                except Exception:
                    pass
        
        if create_date is None:
            return True
        
        if start_time:
            start_date = datetime.strptime(start_time, '%Y-%m-%d')
            if create_date < start_date:
                return False
        
        if end_time:
            end_date = datetime.strptime(end_time, '%Y-%m-%d')
            if create_date > end_date:
                return False
        
        return True
    
    async def run(self):
        """运行下载器"""
        # 显示启动信息
        console.print(Panel.fit(
            "[bold cyan]抖音下载器 v3.0 - 统一增强版[/bold cyan]\n"
            "[dim]支持视频、图文、用户主页、合集批量下载[/dim]",
            border_style="cyan"
        ))

        # 初始化Cookie与请求头
        await self._initialize_cookies_and_headers()

        # 获取URL列表
        urls = self.config.get('link', [])
        # 兼容：单条字符串
        if isinstance(urls, str):
            urls = [urls]
        if not urls:
            console.print("[red]没有找到要下载的链接！[/red]")
            return

        # 分析URL类型
        console.print(f"\n[cyan]📊 链接分析[/cyan]")
        url_types = {}
        for url in urls:
            content_type = self.detect_content_type(url)
            url_types[url] = content_type
            console.print(f"  • {content_type.upper()}: {url[:50]}...")

        # 开始下载
        console.print(f"\n[bold green]⏳ 开始下载 {len(urls)} 个链接[/bold green]\n")

        # 简化进度显示，避免Progress冲突
        for i, url in enumerate(urls, 1):
            content_type = url_types[url]
            console.print(f"\n[{i}/{len(urls)}] 处理: {url}")

            if content_type == ContentType.VIDEO or content_type == ContentType.IMAGE:
                # 为单个视频/图文创建独立的Progress
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(bar_width=40),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    console=console,
                    transient=True
                ) as progress:
                    task = progress.add_task("正在下载...", total=100)
                    await self.download_single_video(url, progress, task)

            elif content_type == ContentType.USER:
                await self.download_user_page(url)
            elif content_type == ContentType.MIX:
                await self.download_mix(url)
            elif content_type == ContentType.MUSIC:
                await self.download_music(url)
            else:
                console.print(f"[yellow]不支持的内容类型: {content_type}[/yellow]")

            # 显示进度
            console.print(f"[dim]进度: {i}/{len(urls)} | 成功: {self.stats.success} | 失败: {self.stats.failed}[/dim]")

        # 显示统计
        self._show_stats()
    
    def _show_stats(self):
        """显示下载统计"""
        console.print("\n" + "=" * 60)
        
        # 创建统计表格
        table = Table(title="📊 下载统计", show_header=True, header_style="bold magenta")
        table.add_column("项目", style="cyan", width=12)
        table.add_column("数值", style="green")
        
        stats = self.stats.to_dict()
        table.add_row("总任务数", str(stats['total']))
        table.add_row("成功", str(stats['success']))
        table.add_row("失败", str(stats['failed']))
        table.add_row("跳过", str(stats['skipped']))
        table.add_row("成功率", stats['success_rate'])
        table.add_row("用时", stats['elapsed_time'])
        
        console.print(table)
        console.print("\n[bold green]✅ 下载任务完成！[/bold green]")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='抖音下载器 - 统一增强版',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-c', '--config',
        default='config_downloader.yml',
        help='配置文件路径 (默认: config_downloader.yml)'
    )
    
    parser.add_argument(
        '-u', '--url',
        nargs='+',
        help='直接指定要下载的URL'
    )
    parser.add_argument(
        '-p', '--path',
        default=None,
        help='保存路径 (覆盖配置文件)'
    )
    parser.add_argument(
        '--auto-cookie',
        action='store_true',
        help='自动获取Cookie（需要已安装Playwright）'
    )
    parser.add_argument(
        '--cookie',
        help='手动指定Cookie字符串，例如 "msToken=xxx; ttwid=yyy"'
    )
    
    args = parser.parse_args()
    
    # 组合配置来源：优先命令行
    temp_config = {}
    if args.url:
        temp_config['link'] = args.url
    
    # 覆盖保存路径
    if args.path:
        temp_config['path'] = args.path
    
    # Cookie配置
    if args.auto_cookie:
        temp_config['auto_cookie'] = True
        temp_config['cookies'] = 'auto'
    if args.cookie:
        temp_config['cookies'] = args.cookie
        temp_config['auto_cookie'] = False
    
    # 如果存在临时配置，则生成一个临时文件供现有构造函数使用
    if temp_config:
        # 合并文件配置（如存在）
        file_config = {}
        if os.path.exists(args.config):
            try:
                with open(args.config, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
            except Exception:
                file_config = {}
        
        # 兼容简化键名
        if 'links' in file_config and 'link' not in file_config:
            file_config['link'] = file_config['links']
        if 'output_dir' in file_config and 'path' not in file_config:
            file_config['path'] = file_config['output_dir']
        if 'cookie' in file_config and 'cookies' not in file_config:
            file_config['cookies'] = file_config['cookie']
        
        merged = {**(file_config or {}), **temp_config}
        with open('temp_config.yml', 'w', encoding='utf-8') as f:
            yaml.dump(merged, f, allow_unicode=True)
        config_path = 'temp_config.yml'
    else:
        config_path = args.config
    
    # 运行下载器
    try:
        downloader = UnifiedDownloader(config_path)
        asyncio.run(downloader.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ 用户中断下载[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ 程序异常: {e}[/red]")
        logger.exception("程序异常")
    finally:
        # 清理临时配置
        if args.url and os.path.exists('temp_config.yml'):
            os.remove('temp_config.yml')


if __name__ == '__main__':
    main()