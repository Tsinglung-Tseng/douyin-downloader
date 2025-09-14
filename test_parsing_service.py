#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试解析服务
"""

import requests
import json
import time
import asyncio

# 服务地址
BASE_URL = "http://localhost:5000"


def test_health():
    """测试健康检查"""
    print("\n=== 测试健康检查 ===")
    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    return response.status_code == 200


def test_single_parse():
    """测试单个视频解析"""
    print("\n=== 测试单个视频解析 ===")

    # 测试URL
    test_urls = [
        "https://v.douyin.com/gNv_ZvhuEr0/",  # 短链接
        "https://www.douyin.com/video/7549035040701844779",  # 长链接
    ]

    for url in test_urls:
        print(f"\n测试URL: {url}")

        data = {
            "url": url,
            "use_proxy": False,
            "force_refresh": False
        }

        try:
            response = requests.post(
                f"{BASE_URL}/parse",
                json=data,
                timeout=60
            )

            print(f"状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    video_data = result.get('data', {})
                    print(f"✅ 解析成功!")
                    print(f"  视频ID: {video_data.get('video_id')}")
                    print(f"  标题: {video_data.get('title', '')[:50]}")
                    print(f"  作者: {video_data.get('author')}")
                    print(f"  视频URL: {video_data.get('video_url', '')[:80]}")
                else:
                    print(f"❌ 解析失败: {result.get('error')}")
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                print(f"响应: {response.text[:500]}")

        except requests.Timeout:
            print("❌ 请求超时")
        except Exception as e:
            print(f"❌ 错误: {e}")

        time.sleep(2)  # 避免请求过快


def test_batch_parse():
    """测试批量解析"""
    print("\n=== 测试批量解析 ===")

    urls = [
        "https://v.douyin.com/gNv_ZvhuEr0/",
        "https://www.douyin.com/video/7549035040701844779",
    ]

    data = {
        "urls": urls,
        "use_proxy": False
    }

    try:
        response = requests.post(
            f"{BASE_URL}/batch_parse",
            json=data,
            timeout=120
        )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                results = result.get('results', [])
                print(f"处理了 {len(results)} 个URL")

                for item in results:
                    url = item.get('url')
                    if item.get('success'):
                        print(f"✅ {url}: 成功")
                    else:
                        print(f"❌ {url}: {item.get('error')}")
            else:
                print(f"批量解析失败: {result.get('error')}")
        else:
            print(f"HTTP错误: {response.status_code}")

    except Exception as e:
        print(f"错误: {e}")


def test_stats():
    """测试统计信息"""
    print("\n=== 测试统计信息 ===")

    try:
        response = requests.get(f"{BASE_URL}/stats")
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            stats = response.json()
            print("\n统计信息:")
            print(f"策略状态: {json.dumps(stats.get('strategies', {}), indent=2)}")
            print(f"缓存统计: {json.dumps(stats.get('cache_stats', {}), indent=2)}")
            print(f"指标: {json.dumps(stats.get('metrics', {}), indent=2)}")
        else:
            print(f"获取统计失败: {response.status_code}")

    except Exception as e:
        print(f"错误: {e}")


def test_with_cookies():
    """测试带Cookie的请求"""
    print("\n=== 测试带Cookie的请求 ===")

    # 读取Cookie（如果有）
    cookies = {}
    try:
        with open('cookies.txt', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
    except:
        print("没有找到cookies.txt文件，跳过Cookie测试")
        return

    data = {
        "url": "https://www.douyin.com/video/7549035040701844779",
        "cookies": cookies,
        "force_refresh": True
    }

    try:
        response = requests.post(
            f"{BASE_URL}/parse",
            json=data,
            timeout=60
        )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ 带Cookie解析成功")
            else:
                print(f"❌ 解析失败: {result.get('error')}")
        else:
            print(f"❌ HTTP错误: {response.status_code}")

    except Exception as e:
        print(f"错误: {e}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试解析服务")
    print("=" * 60)

    # 测试服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ 服务未运行，请先启动服务:")
            print("   cd parsing_service && python app.py")
            print("   或使用Docker: docker-compose up")
            return
    except:
        print("❌ 无法连接到服务，请确保服务正在运行")
        return

    # 运行测试
    test_health()
    test_single_parse()
    test_batch_parse()
    test_stats()
    test_with_cookies()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()