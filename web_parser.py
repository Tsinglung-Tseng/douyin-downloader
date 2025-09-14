#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音网页解析器 - 从HTML页面提取视频信息
基于yt-dlp的思路，直接解析网页中的数据
"""

import re
import json
import base64
import urllib.parse
import requests
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class DouYinWebParser:
    """抖音网页解析器"""

    def __init__(self, cookies: Optional[Dict] = None):
        self.cookies = cookies or {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

    def get_video_info(self, url: str) -> Optional[Dict]:
        """从网页获取视频信息"""
        try:
            # 如果是短链接，先获取重定向后的URL
            if 'v.douyin.com' in url:
                url = self._resolve_short_url(url)

            # 确保是完整的URL
            if not url.startswith('http'):
                if '/video/' in url:
                    url = f'https://www.douyin.com{url}'
                else:
                    url = f'https://www.douyin.com/video/{url}'

            logger.info(f"获取页面: {url}")

            # 请求页面
            response = requests.get(url, headers=self.headers, cookies=self.cookies, timeout=10)

            if response.status_code != 200:
                logger.error(f"页面请求失败: {response.status_code}")
                return None

            html = response.text

            # 尝试多种方法提取数据
            video_info = None

            # 方法1: 从RENDER_DATA提取
            video_info = self._extract_from_render_data(html)
            if video_info:
                logger.info("成功从RENDER_DATA提取视频信息")
                return video_info

            # 方法2: 从SSR数据提取
            video_info = self._extract_from_ssr_data(html)
            if video_info:
                logger.info("成功从SSR_DATA提取视频信息")
                return video_info

            # 方法3: 从SIGI_STATE提取
            video_info = self._extract_from_sigi_state(html)
            if video_info:
                logger.info("成功从SIGI_STATE提取视频信息")
                return video_info

            # 方法4: 从页面JSON提取
            video_info = self._extract_from_page_json(html)
            if video_info:
                logger.info("成功从页面JSON提取视频信息")
                return video_info

            logger.error("无法从页面提取视频信息")
            return None

        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _resolve_short_url(self, url: str) -> str:
        """解析短链接"""
        try:
            response = requests.get(url, headers=self.headers, allow_redirects=False)
            if 'Location' in response.headers:
                location = response.headers['Location']
                # 提取视频ID
                video_id_match = re.search(r'/video/(\d+)', location) or \
                                re.search(r'/share/video/(\d+)', location)
                if video_id_match:
                    video_id = video_id_match.group(1)
                    return f'https://www.douyin.com/video/{video_id}'
                return location
        except:
            pass
        return url

    def _extract_from_render_data(self, html: str) -> Optional[Dict]:
        """从RENDER_DATA提取"""
        try:
            # 查找RENDER_DATA
            match = re.search(r'<script\s+id="RENDER_DATA"\s+type="application/json">([^<]+)</script>', html)
            if not match:
                return None

            # URL解码
            data_str = urllib.parse.unquote(match.group(1))
            data = json.loads(data_str)

            # 遍历查找视频数据
            video_info = self._search_video_in_data(data)
            return video_info

        except Exception as e:
            logger.debug(f"RENDER_DATA解析失败: {e}")
            return None

    def _extract_from_ssr_data(self, html: str) -> Optional[Dict]:
        """从SSR_DATA提取"""
        try:
            # 查找多种可能的SSR数据格式
            patterns = [
                r'window\._SSR_HYDRATED_DATA\s*=\s*({[^;]+});',
                r'<script>window\._SSR_HYDRATED_DATA=({[^<]+})</script>',
            ]

            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    data = json.loads(match.group(1))
                    video_info = self._search_video_in_data(data)
                    if video_info:
                        return video_info

        except Exception as e:
            logger.debug(f"SSR_DATA解析失败: {e}")
            return None

    def _extract_from_sigi_state(self, html: str) -> Optional[Dict]:
        """从SIGI_STATE提取（类似TikTok）"""
        try:
            # 查找SIGI_STATE
            patterns = [
                r'window\[\'SIGI_STATE\'\]\s*=\s*({[^;]+});',
                r'<script>window\.SIGI_STATE=({[^<]+})</script>',
            ]

            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    data = json.loads(match.group(1))
                    # SIGI_STATE通常包含ItemModule
                    if 'ItemModule' in data:
                        for item_id, item_data in data['ItemModule'].items():
                            if self._is_video_data(item_data):
                                return self._format_video_info(item_data)

        except Exception as e:
            logger.debug(f"SIGI_STATE解析失败: {e}")
            return None

    def _extract_from_page_json(self, html: str) -> Optional[Dict]:
        """从页面中的JSON数据提取"""
        try:
            # 查找包含视频信息的JSON
            patterns = [
                r'<script>window\.__INITIAL_STATE__=({[^<]+})</script>',
                r'<script[^>]*>var\s+(?:_)?data\s*=\s*({[^;]+})</script>',
            ]

            for pattern in patterns:
                matches = re.finditer(pattern, html)
                for match in matches:
                    try:
                        data = json.loads(match.group(1))
                        video_info = self._search_video_in_data(data)
                        if video_info:
                            return video_info
                    except:
                        continue

        except Exception as e:
            logger.debug(f"页面JSON解析失败: {e}")
            return None

    def _search_video_in_data(self, data: Any, depth: int = 0) -> Optional[Dict]:
        """递归搜索视频数据"""
        if depth > 10:  # 防止无限递归
            return None

        if isinstance(data, dict):
            # 检查是否是视频数据
            if self._is_video_data(data):
                return self._format_video_info(data)

            # 查找特定键
            for key in ['aweme_detail', 'aweme', 'itemInfo', 'video', 'videoData']:
                if key in data:
                    result = self._search_video_in_data(data[key], depth + 1)
                    if result:
                        return result

            # 递归搜索所有值
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._search_video_in_data(value, depth + 1)
                    if result:
                        return result

        elif isinstance(data, list):
            for item in data:
                result = self._search_video_in_data(item, depth + 1)
                if result:
                    return result

        return None

    def _is_video_data(self, data: Dict) -> bool:
        """判断是否是视频数据"""
        if not isinstance(data, dict):
            return False

        # 检查关键字段
        indicators = ['aweme_id', 'video', 'author', 'desc', 'statistics']
        match_count = sum(1 for key in indicators if key in data)

        # 至少匹配3个关键字段
        return match_count >= 3

    def _format_video_info(self, raw_data: Dict) -> Dict:
        """格式化视频信息"""
        try:
            # 提取基本信息
            video_info = {
                'aweme_id': str(raw_data.get('aweme_id', '')),
                'desc': raw_data.get('desc', ''),
                'create_time': raw_data.get('create_time', 0),
                'author': raw_data.get('author', {}),
                'statistics': raw_data.get('statistics', {}),
                'video': raw_data.get('video', {}),
                'music': raw_data.get('music', {}),
                'images': raw_data.get('images', []),
            }

            # 处理视频URL
            if 'video' in raw_data and isinstance(raw_data['video'], dict):
                # 获取播放地址
                play_addr = raw_data['video'].get('play_addr') or \
                           raw_data['video'].get('playAddr') or \
                           raw_data['video'].get('play_address')

                if play_addr:
                    if isinstance(play_addr, dict):
                        url_list = play_addr.get('url_list') or play_addr.get('urlList', [])
                    elif isinstance(play_addr, str):
                        url_list = [play_addr]
                    else:
                        url_list = []

                    # 转换为无水印URL
                    if url_list:
                        clean_urls = []
                        for url in url_list:
                            if isinstance(url, str):
                                # 替换为无水印版本
                                clean_url = url.replace('playwm', 'play')
                                clean_urls.append(clean_url)

                        if 'play_addr' not in video_info['video']:
                            video_info['video']['play_addr'] = {}
                        video_info['video']['play_addr']['url_list'] = clean_urls

            return video_info

        except Exception as e:
            logger.error(f"格式化视频信息失败: {e}")
            return raw_data


def test_parser():
    """测试解析器"""
    # 读取cookies
    cookies = {}
    try:
        with open('cookies.txt', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
    except:
        pass

    parser = DouYinWebParser(cookies)

    # 测试URL
    test_urls = [
        'https://v.douyin.com/gNv_ZvhuEr0/',
        'https://www.douyin.com/video/7549035040701844779',
    ]

    for url in test_urls:
        print(f"\n测试URL: {url}")
        video_info = parser.get_video_info(url)

        if video_info:
            print(f"✅ 成功获取视频信息")
            print(f"  视频ID: {video_info.get('aweme_id', 'N/A')}")
            print(f"  标题: {video_info.get('desc', '无标题')[:50]}")
            print(f"  作者: {video_info.get('author', {}).get('nickname', '未知')}")

            # 检查视频URL
            video_urls = video_info.get('video', {}).get('play_addr', {}).get('url_list', [])
            if video_urls:
                print(f"  视频URL: {video_urls[0][:80]}...")
            else:
                print("  视频URL: 未找到")
        else:
            print("❌ 获取失败")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_parser()