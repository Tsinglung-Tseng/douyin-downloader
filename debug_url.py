#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import re
from urllib.parse import urlparse

def debug_short_url(url):
    """调试短链接解析过程"""
    print(f"原始URL: {url}")
    print("-" * 50)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    # 第一次请求
    response = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
    print(f"状态码: {response.status_code}")

    if response.status_code in [301, 302, 303, 307, 308]:
        location = response.headers.get('Location', '')
        print(f"重定向到: {location}")

        # 检查视频ID
        if '/share/video/' in location:
            video_id_match = re.search(r'/share/video/(\d+)', location)
            if video_id_match:
                video_id = video_id_match.group(1)
                print(f"✅ 找到视频ID: {video_id}")
                video_url = f"https://www.douyin.com/video/{video_id}"
                print(f"构造URL: {video_url}")
                return video_url

        # 检查其他模式
        patterns = [
            (r'/video/(\d+)', '直接视频'),
            (r'/note/(\d+)', '图文'),
            (r'modal_id=(\d+)', 'modal_id'),
            (r'aweme_id=(\d+)', 'aweme_id'),
            (r'item_id=(\d+)', 'item_id'),
        ]

        for pattern, name in patterns:
            match = re.search(pattern, location)
            if match:
                video_id = match.group(1)
                print(f"✅ 通过{name}找到ID: {video_id}")
                return f"https://www.douyin.com/video/{video_id}"

    print("❌ 未能解析出视频ID")
    return None

# 测试
url = "https://v.douyin.com/gNv_ZvhuEr0/"
result = debug_short_url(url)
print("\n最终结果:", result)