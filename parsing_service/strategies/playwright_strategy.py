#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Playwright策略 - 使用浏览器自动化获取视频信息
"""

import asyncio
import json
import logging
import re
from typing import Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class PlaywrightStrategy(BaseStrategy):
    """使用Playwright浏览器自动化的策略"""

    def __init__(self):
        """初始化Playwright策略"""
        super().__init__()
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def parse(self, url: str, options: Dict = None) -> Dict:
        """
        使用Playwright解析视频信息

        Args:
            url: 视频URL
            options: 解析选项

        Returns:
            视频信息字典
        """
        options = options or {}

        try:
            # 初始化浏览器
            await self._init_browser(options)

            # 创建页面
            page = await self.browser.new_page()

            # 设置请求拦截
            intercepted_data = {}

            async def handle_response(response):
                """拦截API响应"""
                url = response.url
                if 'aweme/v1/web/aweme/detail' in url:
                    try:
                        data = await response.json()
                        if 'aweme_detail' in data:
                            intercepted_data['detail'] = data
                            logger.info("拦截到detail API响应")
                    except:
                        pass
                elif 'aweme/post' in url:
                    try:
                        data = await response.json()
                        if 'aweme_list' in data:
                            intercepted_data['post'] = data
                            logger.info("拦截到post API响应")
                    except:
                        pass

            page.on('response', handle_response)

            # 设置Cookie（如果有）
            if options.get('cookies'):
                await self._set_cookies(page, options['cookies'])

            # 访问页面
            logger.info(f"访问页面: {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # 等待内容加载
            await self._wait_for_content(page)

            # 优先使用拦截的API数据
            if intercepted_data.get('detail'):
                result = intercepted_data['detail']
                await page.close()
                return self.normalize_video_info(result)

            if intercepted_data.get('post'):
                result = intercepted_data['post']
                if result.get('aweme_list'):
                    result = {'aweme_detail': result['aweme_list'][0]}
                    await page.close()
                    return self.normalize_video_info(result)

            # 如果没有拦截到API，尝试从页面提取
            result = await self._extract_from_page(page)

            await page.close()

            if result:
                return self.normalize_video_info(result)

            raise Exception("无法从页面提取视频信息")

        except Exception as e:
            logger.error(f"Playwright策略解析失败: {e}")
            raise

        finally:
            await self._cleanup()

    async def _init_browser(self, options: Dict):
        """初始化浏览器"""
        if not self.browser:
            self.playwright = await async_playwright().start()

            # 浏览器选项
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-web-security',
            ]

            if options.get('proxy'):
                proxy_config = {
                    'server': options['proxy']
                }
                if options.get('proxy_auth'):
                    proxy_config.update({
                        'username': options['proxy_auth']['username'],
                        'password': options['proxy_auth']['password']
                    })
            else:
                proxy_config = None

            # 启动浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=options.get('headless', True),
                args=browser_args,
                proxy=proxy_config
            )

            logger.info("浏览器已启动")

    async def _set_cookies(self, page: Page, cookies):
        """设置Cookie"""
        if isinstance(cookies, dict):
            cookie_list = []
            for name, value in cookies.items():
                cookie_list.append({
                    'name': name,
                    'value': value,
                    'domain': '.douyin.com',
                    'path': '/'
                })
            await page.context.add_cookies(cookie_list)
        elif isinstance(cookies, list):
            await page.context.add_cookies(cookies)

        logger.info(f"已设置{len(cookies)}个Cookie")

    async def _wait_for_content(self, page: Page):
        """等待内容加载"""
        try:
            # 等待视频元素或图片元素
            await page.wait_for_selector('video, .swiper-slide img', timeout=10000)
        except:
            # 如果没有找到，继续尝试其他方法
            pass

        # 等待一下让数据加载
        await asyncio.sleep(2)

    async def _extract_from_page(self, page: Page) -> Optional[Dict]:
        """从页面提取数据"""
        # 尝试多种提取方法
        extractors = [
            self._extract_render_data,
            self._extract_ssr_data,
            self._extract_sigi_state,
            self._extract_from_dom
        ]

        for extractor in extractors:
            try:
                result = await extractor(page)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"提取方法 {extractor.__name__} 失败: {e}")

        return None

    async def _extract_render_data(self, page: Page) -> Optional[Dict]:
        """提取RENDER_DATA"""
        script = """
        () => {
            const scripts = document.querySelectorAll('script');
            for (let script of scripts) {
                if (script.id === 'RENDER_DATA') {
                    try {
                        const data = decodeURIComponent(script.textContent);
                        return JSON.parse(data);
                    } catch (e) {
                        return null;
                    }
                }
            }
            return null;
        }
        """

        data = await page.evaluate(script)
        if data:
            # 解析RENDER_DATA结构
            try:
                # 根据实际结构提取
                for key in data:
                    if 'aweme' in key.lower() and 'detail' in data[key]:
                        return {'aweme_detail': data[key]['detail']}
            except:
                pass

        return None

    async def _extract_ssr_data(self, page: Page) -> Optional[Dict]:
        """提取SSR_DATA"""
        script = """
        () => {
            if (window._SSR_DATA) {
                return window._SSR_DATA;
            }
            // 尝试从全局变量获取
            if (window.SSR_DATA) {
                return window.SSR_DATA;
            }
            return null;
        }
        """

        data = await page.evaluate(script)
        if data:
            try:
                # 解析SSR_DATA结构
                if 'aweme' in data and 'detail' in data['aweme']:
                    return {'aweme_detail': data['aweme']['detail']}
            except:
                pass

        return None

    async def _extract_sigi_state(self, page: Page) -> Optional[Dict]:
        """提取SIGI_STATE"""
        script = """
        () => {
            if (window.SIGI_STATE) {
                return window.SIGI_STATE;
            }
            if (window.__SIGI_STATE) {
                return window.__SIGI_STATE;
            }
            return null;
        }
        """

        data = await page.evaluate(script)
        if data:
            try:
                # 解析SIGI_STATE结构
                if 'ItemModule' in data:
                    # 获取第一个视频的数据
                    for item_id, item_data in data['ItemModule'].items():
                        if item_data:
                            return {'aweme_detail': item_data}
            except:
                pass

        return None

    async def _extract_from_dom(self, page: Page) -> Optional[Dict]:
        """从DOM提取基本信息"""
        script = """
        () => {
            const result = {};

            // 提取标题
            const titleEl = document.querySelector('h1, [class*="title"], [class*="desc"]');
            if (titleEl) {
                result.desc = titleEl.textContent.trim();
            }

            // 提取作者
            const authorEl = document.querySelector('[class*="author"], [class*="nickname"]');
            if (authorEl) {
                result.author = {
                    nickname: authorEl.textContent.trim()
                };
            }

            // 提取视频URL
            const videoEl = document.querySelector('video');
            if (videoEl) {
                result.video = {
                    play_addr: {
                        url_list: [videoEl.src]
                    }
                };
            }

            // 提取统计信息
            const stats = {};
            const likeEl = document.querySelector('[class*="like"] span, [class*="digg"] span');
            if (likeEl) {
                stats.digg_count = parseInt(likeEl.textContent.replace(/[^0-9]/g, '')) || 0;
            }

            const commentEl = document.querySelector('[class*="comment"] span');
            if (commentEl) {
                stats.comment_count = parseInt(commentEl.textContent.replace(/[^0-9]/g, '')) || 0;
            }

            if (Object.keys(stats).length > 0) {
                result.statistics = stats;
            }

            return Object.keys(result).length > 0 ? {aweme_detail: result} : null;
        }
        """

        return await page.evaluate(script)

    async def _cleanup(self):
        """清理资源"""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.error(f"清理资源失败: {e}")