#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API策略 - 使用签名算法直接调用抖音API
"""

import asyncio
import aiohttp
import json
import time
import random
import string
import logging
from typing import Dict, Optional
from .base_strategy import BaseStrategy
import sys
import os

# 添加父目录到路径以导入签名生成器
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from xbogus_generator import generate_x_bogus, generate_a_bogus

logger = logging.getLogger(__name__)


class APIStrategy(BaseStrategy):
    """使用签名算法的API策略"""

    def __init__(self):
        """初始化API策略"""
        super().__init__()
        self.base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    async def parse(self, url: str, options: Dict = None) -> Dict:
        """
        使用API解析视频信息

        Args:
            url: 视频URL
            options: 解析选项

        Returns:
            视频信息字典
        """
        options = options or {}

        try:
            # 提取视频ID
            video_id = await self._extract_video_id(url)
            if not video_id:
                raise ValueError(f"无法从URL提取视频ID: {url}")

            logger.info(f"提取到视频ID: {video_id}")

            # 尝试多个API端点
            endpoints = [
                self._try_detail_api,
                self._try_post_api,
                self._try_comment_api
            ]

            for endpoint in endpoints:
                try:
                    result = await endpoint(video_id, options)
                    if result and self._validate_result(result):
                        return self.normalize_video_info(result)
                except Exception as e:
                    logger.warning(f"端点 {endpoint.__name__} 失败: {e}")
                    continue

            raise Exception("所有API端点都失败了")

        except Exception as e:
            logger.error(f"API策略解析失败: {e}")
            raise

    async def _extract_video_id(self, url: str) -> Optional[str]:
        """提取视频ID"""
        # 如果是短链接，先解析
        if 'v.douyin.com' in url:
            video_id = await self._resolve_short_url(url)
            if video_id:
                return video_id

        # 从URL提取ID
        video_id = self.extract_video_id(url)
        return video_id

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
                        return self.extract_video_id(location)
        except Exception as e:
            logger.error(f"短链接解析失败: {e}")
        return None

    async def _try_detail_api(self, video_id: str, options: Dict) -> Dict:
        """尝试detail API"""
        params = self._build_params(video_id)

        # 生成X-Bogus签名
        params_str = '&'.join([f"{k}={v}" for k, v in params.items()])
        x_bogus = generate_x_bogus(params_str, self.user_agent)

        # 构建完整URL
        full_url = f"{self.base_url}?{params_str}&X-Bogus={x_bogus}"

        # 构建请求头
        headers = self._build_headers(video_id, options)

        # 发送请求
        async with aiohttp.ClientSession() as session:
            async with session.get(
                full_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'aweme_detail' in data:
                        return data
                    elif 'status_code' in data:
                        logger.warning(f"API返回错误: {data.get('status_msg', 'Unknown')}")

                raise Exception(f"API请求失败: {response.status}")

    async def _try_post_api(self, video_id: str, options: Dict) -> Dict:
        """尝试post API"""
        url = "https://www.douyin.com/aweme/v1/web/aweme/post/"

        data = {
            "aweme_id": video_id,
            "version_code": "170400",
            "device_platform": "webapp"
        }

        headers = self._build_headers(video_id, options)
        headers['Content-Type'] = 'application/json'

        # 生成A-Bogus签名
        a_bogus = generate_a_bogus(data, headers)
        headers['A-Bogus'] = a_bogus

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'aweme_list' in data and data['aweme_list']:
                        return {'aweme_detail': data['aweme_list'][0]}

                raise Exception(f"POST API失败: {response.status}")

    async def _try_comment_api(self, video_id: str, options: Dict) -> Dict:
        """尝试comment API获取基本信息"""
        url = "https://www.douyin.com/aweme/v1/web/comment/list/"

        params = {
            'aweme_id': video_id,
            'cursor': '0',
            'count': '1',
            'device_platform': 'webapp',
            'aid': '6383'
        }

        params_str = '&'.join([f"{k}={v}" for k, v in params.items()])
        x_bogus = generate_x_bogus(params_str, self.user_agent)

        full_url = f"{url}?{params_str}&X-Bogus={x_bogus}"
        headers = self._build_headers(video_id, options)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                full_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # 从评论API可能获取到部分视频信息
                    if 'comments' in data:
                        # 构造基本信息
                        return self._build_from_comment_data(data, video_id)

                raise Exception(f"Comment API失败: {response.status}")

    def _build_params(self, video_id: str) -> Dict:
        """构建请求参数"""
        mstoken = ''.join(random.choices(string.ascii_letters + string.digits + '-_=', k=107))

        return {
            'aweme_id': video_id,
            'device_platform': 'webapp',
            'aid': '6383',
            'channel': 'channel_pc_web',
            'pc_client_type': '1',
            'version_code': '170400',
            'version_name': '17.4.0',
            'cookie_enabled': 'true',
            'screen_width': '1920',
            'screen_height': '1080',
            'browser_language': 'zh-CN',
            'browser_platform': 'MacIntel',
            'browser_name': 'Chrome',
            'browser_version': '122.0.0.0',
            'browser_online': 'true',
            'engine_name': 'Blink',
            'engine_version': '122.0.0.0',
            'os_name': 'Mac OS',
            'os_version': '10.15.7',
            'cpu_core_num': '8',
            'device_memory': '8',
            'platform': 'PC',
            'downlink': '10',
            'effective_type': '4g',
            'round_trip_time': '50',
            'msToken': mstoken
        }

    def _build_headers(self, video_id: str, options: Dict) -> Dict:
        """构建请求头"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f'https://www.douyin.com/video/{video_id}',
            'Origin': 'https://www.douyin.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
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

        return headers

    def _validate_result(self, result: Dict) -> bool:
        """验证结果有效性"""
        if not result:
            return False

        if 'aweme_detail' in result:
            detail = result['aweme_detail']
            # 检查必要字段
            if detail.get('aweme_id') and detail.get('desc'):
                return True

        return False

    def _build_from_comment_data(self, data: Dict, video_id: str) -> Dict:
        """从评论数据构建基本信息"""
        # 这是一个fallback方案，从评论API获取部分信息
        return {
            'aweme_detail': {
                'aweme_id': video_id,
                'desc': '视频信息获取受限',
                'author': {},
                'video': {},
                'statistics': {},
                'create_time': int(time.time())
            }
        }