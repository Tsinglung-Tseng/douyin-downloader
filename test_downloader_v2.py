#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试脚本 - 验证downloader_v2.py的功能
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from downloader_v2 import EnhancedDownloader, URLExtractor, CookieHelper
from apiproxy.douyin.auth.browser_cookies import get_browser_cookies
from rich.console import Console

console = Console()


async def test_url_extraction():
    """测试URL提取功能"""
    console.print("\n[bold cyan]测试1: URL提取和识别[/bold cyan]")

    test_cases = [
        "https://www.douyin.com/video/7123456789",
        "https://v.douyin.com/abc123",
        "https://www.douyin.com/user/MS4wLjABAAAA",
        "8.43 abc:/ 复制打开抖音",
        "分享一个视频 https://www.douyin.com/note/7123456 很好看",
    ]

    extractor = URLExtractor()

    for text in test_cases:
        console.print(f"\n输入: {text}")
        results = extractor.extract_from_text(text)
        if results:
            for r in results:
                console.print(f"  ✓ 类型: {r['type']}, ID: {r.get('id', 'N/A')}")
        else:
            # 尝试提取分享ID
            share_id = extractor.extract_id_from_share_text(text)
            if share_id:
                console.print(f"  ✓ 分享ID: {share_id}")
            else:
                console.print("  ✗ 无法识别")


async def test_cookie_extraction():
    """测试Cookie提取功能"""
    console.print("\n[bold cyan]测试2: Cookie提取[/bold cyan]")

    browsers = ['chrome', 'edge', 'firefox']

    for browser in browsers:
        try:
            console.print(f"\n尝试从{browser}提取...")
            cookies = get_browser_cookies(browser, '.douyin.com')

            if cookies:
                console.print(f"  ✓ 成功提取 {len(cookies)} 个Cookie")

                # 检查关键Cookie
                important = ['msToken', 'ttwid', 'sessionid']
                for key in important:
                    if key in cookies:
                        console.print(f"    • {key}: {cookies[key][:20]}...")
                    else:
                        console.print(f"    • {key}: 未找到")
            else:
                console.print(f"  ✗ 未提取到Cookie")

        except Exception as e:
            console.print(f"  ✗ 错误: {e}")


async def test_video_download():
    """测试视频下载功能"""
    console.print("\n[bold cyan]测试3: 视频信息获取（不实际下载）[/bold cyan]")

    # 创建下载器
    downloader = EnhancedDownloader()

    # 测试视频ID
    test_video_ids = [
        "7123456789",  # 示例ID，需要替换为实际的
    ]

    for video_id in test_video_ids:
        console.print(f"\n测试视频ID: {video_id}")
        try:
            # 获取视频信息
            video_info = await downloader._get_video_info_with_fallback(video_id)

            if video_info:
                console.print("  ✓ 成功获取视频信息")
                console.print(f"    标题: {video_info.get('desc', '无标题')[:50]}")
                console.print(f"    作者: {video_info.get('author', {}).get('nickname', 'unknown')}")

                # 检查媒体类型
                if video_info.get('images'):
                    console.print(f"    类型: 图文 ({len(video_info['images'])} 张)")
                else:
                    console.print("    类型: 视频")

                # 检查URL
                video_url = downloader._get_no_watermark_url(video_info)
                if video_url:
                    console.print(f"    视频URL: {video_url[:50]}...")
            else:
                console.print("  ✗ 无法获取视频信息")

        except Exception as e:
            console.print(f"  ✗ 错误: {e}")


async def test_short_url_resolve():
    """测试短链接解析"""
    console.print("\n[bold cyan]测试4: 短链接解析[/bold cyan]")

    downloader = EnhancedDownloader()

    # 测试短链接（需要实际的短链接）
    test_urls = [
        "https://v.douyin.com/test",  # 示例，需要替换
    ]

    for url in test_urls:
        console.print(f"\n短链接: {url}")
        try:
            resolved = await downloader.resolve_short_url(url)
            if resolved != url:
                console.print(f"  ✓ 解析成功: {resolved[:80]}...")
            else:
                console.print("  ✗ 解析失败")
        except Exception as e:
            console.print(f"  ✗ 错误: {e}")


async def run_all_tests():
    """运行所有测试"""
    console.print("[bold green]===== 开始测试 =====[/bold green]")

    # 测试URL提取
    await test_url_extraction()

    # 测试Cookie提取
    await test_cookie_extraction()

    # 测试视频下载
    await test_video_download()

    # 测试短链接
    await test_short_url_resolve()

    console.print("\n[bold green]===== 测试完成 =====[/bold green]")


async def quick_test():
    """快速功能测试"""
    console.print("[bold yellow]快速功能测试[/bold yellow]")

    # 1. 测试URL识别
    extractor = URLExtractor()
    test_url = "https://www.douyin.com/video/7123456789"
    result = extractor.parse_url(test_url)
    if result and result['type'] == 'video':
        console.print("✓ URL识别: 通过")
    else:
        console.print("✗ URL识别: 失败")

    # 2. 测试Cookie提取（尝试Chrome）
    try:
        cookies = get_browser_cookies('chrome', '.douyin.com')
        if cookies:
            console.print(f"✓ Cookie提取: 通过 ({len(cookies)} 个)")
        else:
            console.print("✗ Cookie提取: 无Cookie")
    except Exception as e:
        console.print(f"✗ Cookie提取: {e}")

    # 3. 测试下载器初始化
    try:
        downloader = EnhancedDownloader()
        console.print("✓ 下载器初始化: 通过")
    except Exception as e:
        console.print(f"✗ 下载器初始化: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试下载器功能")
    parser.add_argument('--quick', action='store_true', help='快速测试')
    parser.add_argument('--full', action='store_true', help='完整测试')

    args = parser.parse_args()

    if args.quick:
        asyncio.run(quick_test())
    else:
        asyncio.run(run_all_tests())