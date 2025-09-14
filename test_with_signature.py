#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试使用X-Bogus签名获取视频信息
"""

import requests
import json
import time
from xbogus_generator import generate_x_bogus, generate_a_bogus


def test_video_api(video_id: str, use_cookies: bool = True):
    """测试视频API"""

    # 构建参数
    params = {
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
    }

    # 添加msToken
    import random
    import string
    mstoken = ''.join(random.choices(string.ascii_letters + string.digits + '-_=', k=107))
    params['msToken'] = mstoken

    # User-Agent
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    # 生成X-Bogus
    params_str = '&'.join([f"{k}={v}" for k, v in params.items()])
    x_bogus = generate_x_bogus(params_str, user_agent)

    print(f"Generated X-Bogus: {x_bogus}")

    # 构建完整URL
    base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
    full_url = f"{base_url}?{params_str}&X-Bogus={x_bogus}"

    # 请求头
    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': f'https://www.douyin.com/video/{video_id}',
        'Origin': 'https://www.douyin.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    # 读取Cookie（如果有）
    cookies = {}
    if use_cookies:
        try:
            with open('cookies.txt', 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        parts = line.strip().split('\t')
                        if len(parts) >= 7:
                            cookies[parts[5]] = parts[6]
            print(f"Loaded {len(cookies)} cookies")

            # Cookie字符串
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            headers['Cookie'] = cookie_str
        except Exception as e:
            print(f"Failed to load cookies: {e}")

    # 发送请求
    print(f"\nRequesting: {base_url}")
    print(f"Video ID: {video_id}")

    try:
        response = requests.get(full_url, headers=headers, timeout=10)

        print(f"Status Code: {response.status_code}")
        print(f"Response Length: {len(response.text)}")

        if response.status_code == 200:
            try:
                data = response.json()

                if 'aweme_detail' in data:
                    video_info = data['aweme_detail']
                    print("\n✅ Successfully retrieved video info!")
                    print(f"Title: {video_info.get('desc', 'No title')[:50]}")
                    print(f"Author: {video_info.get('author', {}).get('nickname', 'Unknown')}")

                    # 检查视频URL
                    video = video_info.get('video', {})
                    if 'play_addr' in video:
                        urls = video['play_addr'].get('url_list', [])
                        if urls:
                            print(f"Video URL: {urls[0][:80]}...")

                    return video_info

                elif 'status_code' in data:
                    print(f"\n❌ API Error: {data.get('status_msg', 'Unknown error')}")
                    print(f"Status Code: {data['status_code']}")

                else:
                    print("\n❌ Unexpected response format")
                    print(json.dumps(data, indent=2)[:500])

            except json.JSONDecodeError:
                print("\n❌ Response is not JSON")
                print(response.text[:500])

        else:
            print(f"\n❌ HTTP Error: {response.status_code}")

    except Exception as e:
        print(f"\n❌ Request failed: {e}")

    return None


def test_with_a_bogus(video_id: str):
    """测试使用A-Bogus"""
    print("\n" + "="*50)
    print("Testing with A-Bogus")
    print("="*50)

    # 构建请求数据
    data = {
        "aweme_id": video_id,
        "version_code": "170400",
        "device_platform": "webapp"
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': f'https://www.douyin.com/video/{video_id}',
        'Content-Type': 'application/json'
    }

    # 生成A-Bogus
    a_bogus = generate_a_bogus(data, headers)
    print(f"Generated A-Bogus: {a_bogus}")

    # 添加到头部
    headers['A-Bogus'] = a_bogus

    # 尝试POST请求
    url = "https://www.douyin.com/aweme/v1/web/aweme/post/"

    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    # 测试视频ID
    video_id = "7549035040701844779"

    print("="*50)
    print("Testing DouYin API with X-Bogus")
    print("="*50)

    # 测试不带Cookie
    print("\n1. Testing without cookies:")
    test_video_api(video_id, use_cookies=False)

    # 测试带Cookie
    print("\n" + "="*50)
    print("2. Testing with cookies:")
    test_video_api(video_id, use_cookies=True)

    # 测试A-Bogus
    test_with_a_bogus(video_id)