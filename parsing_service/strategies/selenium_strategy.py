#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Selenium策略 - 使用Selenium浏览器自动化获取视频信息
"""

import asyncio
import json
import logging
import re
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from .base_strategy import BaseStrategy
import concurrent.futures

logger = logging.getLogger(__name__)


class SeleniumStrategy(BaseStrategy):
    """使用Selenium浏览器自动化的策略"""

    def __init__(self):
        """初始化Selenium策略"""
        super().__init__()
        self.driver: Optional[webdriver.Chrome] = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def parse(self, url: str, options: Dict = None) -> Dict:
        """
        使用Selenium解析视频信息

        Args:
            url: 视频URL
            options: 解析选项

        Returns:
            视频信息字典
        """
        options = options or {}

        try:
            # 在线程池中运行Selenium（因为Selenium是同步的）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._parse_sync,
                url,
                options
            )

            if result:
                return self.normalize_video_info(result)

            raise Exception("无法从页面提取视频信息")

        except Exception as e:
            logger.error(f"Selenium策略解析失败: {e}")
            raise

    def _parse_sync(self, url: str, options: Dict) -> Dict:
        """同步解析方法"""
        try:
            # 初始化驱动
            self._init_driver(options)

            # 设置Cookie
            if options.get('cookies'):
                self._set_cookies(options['cookies'])

            # 访问页面
            logger.info(f"访问页面: {url}")
            self.driver.get(url)

            # 等待页面加载
            self._wait_for_content()

            # 提取数据
            result = self._extract_data()

            return result

        finally:
            self._cleanup_sync()

    def _init_driver(self, options: Dict):
        """初始化驱动"""
        if not self.driver:
            chrome_options = Options()

            # 基本选项
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # 无头模式
            if options.get('headless', True):
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')

            # 其他优化选项
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')

            # User-Agent
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')

            # 代理设置
            if options.get('proxy'):
                chrome_options.add_argument(f'--proxy-server={options["proxy"]}')

            # 创建驱动
            self.driver = webdriver.Chrome(options=chrome_options)

            # 执行反检测脚本
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })

            logger.info("Selenium驱动已初始化")

    def _set_cookies(self, cookies):
        """设置Cookie"""
        # 先访问域名设置cookie
        self.driver.get("https://www.douyin.com")

        if isinstance(cookies, dict):
            for name, value in cookies.items():
                self.driver.add_cookie({
                    'name': name,
                    'value': value,
                    'domain': '.douyin.com'
                })
        elif isinstance(cookies, list):
            for cookie in cookies:
                self.driver.add_cookie(cookie)

        logger.info(f"已设置{len(cookies)}个Cookie")

    def _wait_for_content(self):
        """等待内容加载"""
        wait = WebDriverWait(self.driver, 10)

        try:
            # 等待视频或图片元素
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "video, .swiper-slide img")
                )
            )
        except TimeoutException:
            logger.warning("等待内容超时，继续尝试提取")

        # 额外等待让JavaScript执行
        import time
        time.sleep(3)

    def _extract_data(self) -> Optional[Dict]:
        """提取数据"""
        # 尝试多种提取方法
        extractors = [
            self._extract_from_network,
            self._extract_render_data,
            self._extract_ssr_data,
            self._extract_sigi_state,
            self._extract_from_dom
        ]

        for extractor in extractors:
            try:
                result = extractor()
                if result:
                    return result
            except Exception as e:
                logger.warning(f"提取方法 {extractor.__name__} 失败: {e}")

        return None

    def _extract_from_network(self) -> Optional[Dict]:
        """从网络请求提取（通过performance API）"""
        script = """
        return window.performance.getEntriesByType('resource')
            .filter(e => e.name.includes('aweme/v1/web/aweme/detail'))
            .map(e => e.name);
        """

        urls = self.driver.execute_script(script)

        # 如果找到API请求，尝试获取响应
        # 注：Selenium原生不支持拦截响应，这里只是获取URL
        if urls:
            logger.info(f"发现API请求: {urls[0]}")

        return None

    def _extract_render_data(self) -> Optional[Dict]:
        """提取RENDER_DATA"""
        script = """
        const scripts = document.querySelectorAll('script');
        for (let script of scripts) {
            if (script.id === 'RENDER_DATA') {
                try {
                    return decodeURIComponent(script.textContent);
                } catch (e) {
                    return null;
                }
            }
        }
        return null;
        """

        data_str = self.driver.execute_script(script)
        if data_str:
            try:
                data = json.loads(data_str)
                # 解析RENDER_DATA结构
                for key in data:
                    if 'aweme' in key.lower():
                        if 'detail' in data[key]:
                            return {'aweme_detail': data[key]['detail']}
                        elif 'aweme_detail' in data[key]:
                            return {'aweme_detail': data[key]['aweme_detail']}
            except Exception as e:
                logger.error(f"解析RENDER_DATA失败: {e}")

        return None

    def _extract_ssr_data(self) -> Optional[Dict]:
        """提取SSR_DATA"""
        script = """
        if (window._SSR_DATA) {
            return window._SSR_DATA;
        }
        if (window.SSR_DATA) {
            return window.SSR_DATA;
        }
        return null;
        """

        data = self.driver.execute_script(script)
        if data:
            try:
                if isinstance(data, str):
                    data = json.loads(data)

                if 'aweme' in data and 'detail' in data['aweme']:
                    return {'aweme_detail': data['aweme']['detail']}
            except Exception as e:
                logger.error(f"解析SSR_DATA失败: {e}")

        return None

    def _extract_sigi_state(self) -> Optional[Dict]:
        """提取SIGI_STATE"""
        script = """
        if (window.SIGI_STATE) {
            return window.SIGI_STATE;
        }
        if (window.__SIGI_STATE) {
            return window.__SIGI_STATE;
        }
        return null;
        """

        data = self.driver.execute_script(script)
        if data:
            try:
                if isinstance(data, str):
                    data = json.loads(data)

                if 'ItemModule' in data:
                    # 获取第一个视频的数据
                    for item_id, item_data in data['ItemModule'].items():
                        if item_data:
                            return {'aweme_detail': item_data}
            except Exception as e:
                logger.error(f"解析SIGI_STATE失败: {e}")

        return None

    def _extract_from_dom(self) -> Optional[Dict]:
        """从DOM提取基本信息"""
        result = {'aweme_detail': {}}
        detail = result['aweme_detail']

        try:
            # 提取标题
            title_selectors = ['h1', '[class*="title"]', '[class*="desc"]']
            for selector in title_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        detail['desc'] = element.text.strip()
                        break
                except:
                    continue

            # 提取作者
            author_selectors = ['[class*="author"]', '[class*="nickname"]']
            for selector in author_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        detail['author'] = {'nickname': element.text.strip()}
                        break
                except:
                    continue

            # 提取视频URL
            try:
                video = self.driver.find_element(By.TAG_NAME, 'video')
                if video:
                    src = video.get_attribute('src')
                    if src:
                        detail['video'] = {
                            'play_addr': {
                                'url_list': [src]
                            }
                        }
            except:
                pass

            # 提取统计信息
            stats = {}

            # 点赞数
            like_selectors = ['[class*="like"] span', '[class*="digg"] span']
            for selector in like_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        text = element.text.strip()
                        count = self._parse_count(text)
                        if count is not None:
                            stats['digg_count'] = count
                            break
                except:
                    continue

            # 评论数
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, '[class*="comment"] span')
                if element:
                    text = element.text.strip()
                    count = self._parse_count(text)
                    if count is not None:
                        stats['comment_count'] = count
            except:
                pass

            if stats:
                detail['statistics'] = stats

            # 如果有基本信息，返回结果
            if detail.get('desc') or detail.get('video'):
                return result

        except Exception as e:
            logger.error(f"从DOM提取失败: {e}")

        return None

    def _parse_count(self, text: str) -> Optional[int]:
        """解析计数文本"""
        try:
            # 移除非数字字符
            text = re.sub(r'[^\d.万亿]', '', text)

            if '万' in text:
                num = float(text.replace('万', ''))
                return int(num * 10000)
            elif '亿' in text:
                num = float(text.replace('亿', ''))
                return int(num * 100000000)
            else:
                return int(float(text))
        except:
            return None

    def _cleanup_sync(self):
        """同步清理资源"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

    async def cleanup(self):
        """异步清理资源"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._cleanup_sync)
        self.executor.shutdown(wait=False)