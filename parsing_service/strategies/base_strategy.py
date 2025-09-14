#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基础策略类
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """解析策略基类"""

    def __init__(self):
        """初始化策略"""
        self.name = self.__class__.__name__

    @abstractmethod
    async def parse(self, url: str, options: Dict = None) -> Dict:
        """
        解析视频信息

        Args:
            url: 视频URL
            options: 解析选项

        Returns:
            视频信息字典
        """
        pass

    def extract_video_id(self, url: str) -> Optional[str]:
        """从URL提取视频ID"""
        import re

        patterns = [
            r'/video/(\d+)',
            r'/note/(\d+)',
            r'modal_id=(\d+)',
            r'aweme_id=(\d+)',
            r'/(\d{15,20})',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # 处理短链接
        if 'v.douyin.com' in url:
            # 需要先解析短链接
            return None

        return None

    def normalize_video_info(self, raw_data: Dict) -> Dict:
        """标准化视频信息"""
        video_info = {
            'video_id': '',
            'title': '',
            'author': '',
            'author_id': '',
            'video_url': '',
            'cover_url': '',
            'music_url': '',
            'duration': 0,
            'create_time': 0,
            'statistics': {
                'likes': 0,
                'comments': 0,
                'shares': 0,
                'views': 0
            },
            'is_image': False,
            'images': [],
            'raw_data': raw_data
        }

        # 根据不同的数据结构提取信息
        if 'aweme_detail' in raw_data:
            detail = raw_data['aweme_detail']
            video_info.update(self._extract_from_aweme_detail(detail))
        elif 'item_list' in raw_data:
            if raw_data['item_list']:
                detail = raw_data['item_list'][0]
                video_info.update(self._extract_from_aweme_detail(detail))
        elif 'aweme_id' in raw_data:
            video_info.update(self._extract_from_aweme_detail(raw_data))

        return video_info

    def _extract_from_aweme_detail(self, detail: Dict) -> Dict:
        """从aweme_detail提取信息"""
        info = {}

        # 基本信息
        info['video_id'] = str(detail.get('aweme_id', ''))
        info['title'] = detail.get('desc', '')
        info['create_time'] = detail.get('create_time', 0)

        # 作者信息
        author = detail.get('author', {})
        info['author'] = author.get('nickname', '')
        info['author_id'] = author.get('sec_uid', '')

        # 统计信息
        stats = detail.get('statistics', {})
        info['statistics'] = {
            'likes': stats.get('digg_count', 0),
            'comments': stats.get('comment_count', 0),
            'shares': stats.get('share_count', 0),
            'views': stats.get('play_count', 0)
        }

        # 视频/图片信息
        if detail.get('images'):
            # 图文作品
            info['is_image'] = True
            info['images'] = []
            for img in detail.get('images', []):
                if isinstance(img, dict):
                    url_list = img.get('url_list', [])
                    if url_list:
                        info['images'].append(url_list[0])
        else:
            # 视频作品
            video = detail.get('video', {})

            # 播放地址
            play_addr = video.get('play_addr', {})
            if play_addr:
                url_list = play_addr.get('url_list', [])
                if url_list:
                    # 替换为无水印版本
                    video_url = url_list[0].replace('playwm', 'play')
                    info['video_url'] = video_url

            # 封面
            cover = video.get('cover', {})
            if cover:
                url_list = cover.get('url_list', [])
                if url_list:
                    info['cover_url'] = url_list[0]

            # 时长
            info['duration'] = video.get('duration', 0)

        # 音乐
        music = detail.get('music', {})
        if music:
            play_url = music.get('play_url', {})
            if play_url:
                url_list = play_url.get('url_list', [])
                if url_list:
                    info['music_url'] = url_list[0]

        return info