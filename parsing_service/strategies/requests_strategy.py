#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Requests策略 - 使用简单HTTP请求获取视频信息
"""

import asyncio
import aiohttp
import json
import re
import logging
from typing import Dict, Optional
from urllib.parse import unquote
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class RequestsStrategy(BaseStrategy):
    """使用简单HTTP请求的策略"""

    def __init__(self):
        """初始化Requests策略"""
        super().__init__()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    async def parse(self, url: str, options: Dict = None) -> Dict:
        """
        使用HTTP请求解析视频信息

        Args:
            url: 视频URL
            options: 解析选项

        Returns:
            视频信息字典
        """
        options = options or {}

        try:
            # 如果是短链接，先解析
            if 'v.douyin.com' in url:
                url = await self._resolve_short_url(url)
                if not url:
                    raise ValueError("无法解析短链接")

            # 获取页面HTML
            html = await self._get_page_html(url, options)

            # 从HTML提取数据
            result = await self._extract_from_html(html)

            if result:
                return self.normalize_video_info(result)

            raise Exception("无法从页面提取视频信息")

        except Exception as e:
            logger.error(f"Requests策略解析失败: {e}")
            raise

    async def _resolve_short_url(self, url: str) -> Optional[str]:
        """解析短链接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    location = response.headers.get('Location', '')
                    if location:
                        logger.info(f"短链接解析: {url} -> {location}")
                        return location
        except Exception as e:
            logger.error(f"短链接解析失败: {e}")

        return None

    async def _get_page_html(self, url: str, options: Dict) -> str:
        """获取页面HTML"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
        }

        # 添加自定义头部
        if options.get('headers'):
            headers.update(options['headers'])

        # 添加Cookie
        if options.get('cookies'):
            if isinstance(options['cookies'], dict):
                cookie_str = '; '.join([f"{k}={v}" for k, v in options['cookies'].items()])
                headers['Cookie'] = cookie_str
            elif isinstance(options['cookies'], str):
                headers['Cookie'] = options['cookies']

        # 代理设置
        proxy = options.get('proxy')

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    raise Exception(f"HTTP请求失败: {response.status}")

                html = await response.text()
                logger.info(f"获取HTML成功，长度: {len(html)}")
                return html

    async def _extract_from_html(self, html: str) -> Optional[Dict]:
        """从HTML提取数据"""
        # 尝试多种提取方法
        extractors = [
            self._extract_render_data,
            self._extract_ssr_data,
            self._extract_sigi_state,
            self._extract_json_ld,
            self._extract_meta_tags
        ]

        for extractor in extractors:
            try:
                result = await extractor(html)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"提取方法 {extractor.__name__} 失败: {e}")

        return None

    async def _extract_render_data(self, html: str) -> Optional[Dict]:
        """提取RENDER_DATA"""
        pattern = r'<script\s+id="RENDER_DATA"\s*>([^<]+)</script>'
        match = re.search(pattern, html)

        if match:
            try:
                encoded_data = match.group(1)
                decoded_data = unquote(encoded_data)
                data = json.loads(decoded_data)

                # 解析RENDER_DATA结构
                for key in data:
                    if 'aweme' in key.lower():
                        if 'detail' in data[key]:
                            logger.info("成功从RENDER_DATA提取数据")
                            return {'aweme_detail': data[key]['detail']}
                        elif 'aweme_detail' in data[key]:
                            logger.info("成功从RENDER_DATA提取数据")
                            return {'aweme_detail': data[key]['aweme_detail']}

            except Exception as e:
                logger.error(f"解析RENDER_DATA失败: {e}")

        return None

    async def _extract_ssr_data(self, html: str) -> Optional[Dict]:
        """提取SSR_DATA"""
        # 尝试多种模式
        patterns = [
            r'window\._SSR_DATA\s*=\s*({[^;]+});',
            r'window\.SSR_DATA\s*=\s*({[^;]+});',
            r'<script>\s*window\._SSR_DATA\s*=\s*({[^<]+})\s*</script>'
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    data_str = match.group(1)
                    data = json.loads(data_str)

                    if 'aweme' in data and 'detail' in data['aweme']:
                        logger.info("成功从SSR_DATA提取数据")
                        return {'aweme_detail': data['aweme']['detail']}

                except Exception as e:
                    logger.error(f"解析SSR_DATA失败: {e}")

        return None

    async def _extract_sigi_state(self, html: str) -> Optional[Dict]:
        """提取SIGI_STATE"""
        patterns = [
            r'window\.SIGI_STATE\s*=\s*({[^;]+});',
            r'window\.__SIGI_STATE\s*=\s*({[^;]+});',
            r'<script>\s*window\.SIGI_STATE\s*=\s*({[^<]+})\s*</script>'
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    data_str = match.group(1)
                    data = json.loads(data_str)

                    if 'ItemModule' in data:
                        # 获取第一个视频的数据
                        for item_id, item_data in data['ItemModule'].items():
                            if item_data:
                                logger.info("成功从SIGI_STATE提取数据")
                                return {'aweme_detail': item_data}

                except Exception as e:
                    logger.error(f"解析SIGI_STATE失败: {e}")

        return None

    async def _extract_json_ld(self, html: str) -> Optional[Dict]:
        """提取JSON-LD结构化数据"""
        pattern = r'<script\s+type="application/ld\+json">([^<]+)</script>'
        matches = re.findall(pattern, html)

        for match in matches:
            try:
                data = json.loads(match)

                # VideoObject类型
                if data.get('@type') == 'VideoObject':
                    result = {
                        'aweme_detail': {
                            'desc': data.get('description', ''),
                            'author': {
                                'nickname': data.get('author', {}).get('name', '')
                            },
                            'video': {
                                'play_addr': {
                                    'url_list': [data.get('contentUrl', '')]
                                }
                            },
                            'statistics': {
                                'digg_count': data.get('interactionStatistic', {}).get('userInteractionCount', 0)
                            }
                        }
                    }

                    if result['aweme_detail']['video']['play_addr']['url_list'][0]:
                        logger.info("成功从JSON-LD提取数据")
                        return result

            except Exception as e:
                logger.error(f"解析JSON-LD失败: {e}")

        return None

    async def _extract_meta_tags(self, html: str) -> Optional[Dict]:
        """从meta标签提取基本信息"""
        result = {'aweme_detail': {}}
        detail = result['aweme_detail']

        # 提取标题
        title_pattern = r'<meta\s+property="og:title"\s+content="([^"]+)"'
        match = re.search(title_pattern, html)
        if match:
            detail['desc'] = match.group(1)

        # 提取视频URL
        video_pattern = r'<meta\s+property="og:video:url"\s+content="([^"]+)"'
        match = re.search(video_pattern, html)
        if match:
            detail['video'] = {
                'play_addr': {
                    'url_list': [match.group(1)]
                }
            }

        # 提取图片（可能是封面）
        image_pattern = r'<meta\s+property="og:image"\s+content="([^"]+)"'
        match = re.search(image_pattern, html)
        if match:
            if 'video' not in detail:
                detail['video'] = {}
            detail['video']['cover'] = {
                'url_list': [match.group(1)]
            }

        # 提取作者
        author_pattern = r'<meta\s+name="author"\s+content="([^"]+)"'
        match = re.search(author_pattern, html)
        if match:
            detail['author'] = {'nickname': match.group(1)}

        # 如果有基本信息，返回结果
        if detail.get('desc') or detail.get('video'):
            logger.info("成功从meta标签提取基本信息")
            return result

        return None