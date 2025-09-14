#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音视频下载器 V3 - 集成解析服务版本
使用独立的解析服务获取视频信息，提高稳定性和成功率
"""

import os
import re
import json
import time
import requests
import asyncio
import aiohttp
from typing import Dict, List, Optional, Union
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DouYinDownloaderV3:
    """抖音下载器V3 - 使用解析服务"""

    def __init__(self, parsing_service_url: str = "http://localhost:5000"):
        """
        初始化下载器

        Args:
            parsing_service_url: 解析服务地址
        """
        self.parsing_service_url = parsing_service_url
        self.session = requests.Session()
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)

        # 配置
        self.config = {
            'max_retries': 3,
            'timeout': 30,
            'chunk_size': 8192,
            'max_workers': 5,
            'use_proxy': False,
            'force_refresh': False
        }

        # 统计信息
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }

        # 检查解析服务
        self._check_parsing_service()

    def _check_parsing_service(self):
        """检查解析服务是否可用"""
        try:
            response = requests.get(f"{self.parsing_service_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ 解析服务正常: {self.parsing_service_url}")
            else:
                logger.warning(f"⚠️ 解析服务响应异常: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ 无法连接到解析服务: {e}")
            logger.error("请先启动解析服务: cd parsing_service && python app.py")
            logger.error("或使用Docker: docker-compose up")
            raise

    def parse_video(self, url: str, cookies: Dict = None) -> Optional[Dict]:
        """
        调用解析服务获取视频信息

        Args:
            url: 视频URL
            cookies: Cookie字典

        Returns:
            视频信息字典
        """
        data = {
            'url': url,
            'use_proxy': self.config['use_proxy'],
            'force_refresh': self.config['force_refresh']
        }

        if cookies:
            data['cookies'] = cookies

        try:
            response = self.session.post(
                f"{self.parsing_service_url}/parse",
                json=data,
                timeout=self.config['timeout']
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return result.get('data')
                else:
                    logger.error(f"解析失败: {result.get('error')}")
            else:
                logger.error(f"解析服务错误: {response.status_code}")

        except Exception as e:
            logger.error(f"调用解析服务失败: {e}")

        return None

    def batch_parse(self, urls: List[str], cookies: Dict = None) -> List[Dict]:
        """
        批量解析视频

        Args:
            urls: URL列表
            cookies: Cookie字典

        Returns:
            解析结果列表
        """
        data = {
            'urls': urls,
            'use_proxy': self.config['use_proxy']
        }

        if cookies:
            data['cookies'] = cookies

        try:
            response = self.session.post(
                f"{self.parsing_service_url}/batch_parse",
                json=data,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return result.get('results', [])

        except Exception as e:
            logger.error(f"批量解析失败: {e}")

        return []

    def download_video(self, video_info: Dict, save_dir: Path = None) -> bool:
        """
        下载视频文件

        Args:
            video_info: 视频信息
            save_dir: 保存目录

        Returns:
            是否成功
        """
        if not video_info:
            return False

        save_dir = save_dir or self.download_dir
        save_dir.mkdir(exist_ok=True)

        # 构建文件名
        video_id = video_info.get('video_id', 'unknown')
        title = self._sanitize_filename(video_info.get('title', video_id))
        author = self._sanitize_filename(video_info.get('author', 'unknown'))

        # 处理图文作品
        if video_info.get('is_image'):
            return self._download_images(video_info, save_dir, title, author)

        # 下载视频
        video_url = video_info.get('video_url')
        if not video_url:
            logger.error(f"没有找到视频URL: {video_id}")
            return False

        filename = f"{author}_{title}_{video_id}.mp4"
        filepath = save_dir / filename

        # 如果文件已存在，跳过
        if filepath.exists():
            logger.info(f"文件已存在，跳过: {filename}")
            self.stats['skipped'] += 1
            return True

        try:
            logger.info(f"开始下载: {filename}")

            # 下载视频
            response = self.session.get(video_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))

            with open(filepath, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename[:30]) as pbar:
                    for chunk in response.iter_content(chunk_size=self.config['chunk_size']):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            logger.info(f"✅ 下载成功: {filename}")
            self.stats['success'] += 1

            # 下载封面（可选）
            cover_url = video_info.get('cover_url')
            if cover_url:
                self._download_cover(cover_url, save_dir, f"{author}_{title}_{video_id}.jpg")

            return True

        except Exception as e:
            logger.error(f"下载失败: {filename} - {e}")
            self.stats['failed'] += 1

            # 清理未完成的文件
            if filepath.exists():
                filepath.unlink()

            return False

    def _download_images(self, video_info: Dict, save_dir: Path, title: str, author: str) -> bool:
        """下载图文作品"""
        images = video_info.get('images', [])
        if not images:
            logger.error("没有找到图片")
            return False

        video_id = video_info.get('video_id', 'unknown')
        image_dir = save_dir / f"{author}_{title}_{video_id}"
        image_dir.mkdir(exist_ok=True)

        logger.info(f"下载图文作品: {len(images)} 张图片")

        success_count = 0
        for i, image_url in enumerate(images, 1):
            try:
                response = self.session.get(image_url, timeout=30)
                response.raise_for_status()

                image_path = image_dir / f"image_{i:02d}.jpg"
                with open(image_path, 'wb') as f:
                    f.write(response.content)

                success_count += 1
                logger.debug(f"下载图片 {i}/{len(images)}")

            except Exception as e:
                logger.error(f"图片下载失败 {i}: {e}")

        if success_count > 0:
            logger.info(f"✅ 图文下载成功: {success_count}/{len(images)} 张")
            self.stats['success'] += 1
            return True
        else:
            self.stats['failed'] += 1
            return False

    def _download_cover(self, cover_url: str, save_dir: Path, filename: str):
        """下载封面图片"""
        try:
            filepath = save_dir / filename
            if not filepath.exists():
                response = self.session.get(cover_url, timeout=10)
                response.raise_for_status()

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                logger.debug(f"封面下载成功: {filename}")
        except Exception as e:
            logger.debug(f"封面下载失败: {e}")

    def download_from_url(self, url: str, cookies: Dict = None) -> bool:
        """
        从URL下载视频

        Args:
            url: 视频URL
            cookies: Cookie字典

        Returns:
            是否成功
        """
        self.stats['total'] += 1

        # 解析视频信息
        video_info = self.parse_video(url, cookies)
        if not video_info:
            logger.error(f"无法解析视频: {url}")
            self.stats['failed'] += 1
            return False

        # 下载视频
        return self.download_video(video_info)

    def download_from_user(self, user_url: str, cookies: Dict = None, max_videos: int = 10):
        """
        下载用户的视频

        Args:
            user_url: 用户主页URL
            cookies: Cookie字典
            max_videos: 最大下载数量
        """
        logger.info(f"下载用户视频: {user_url}")
        logger.warning("用户页面下载需要更复杂的处理，建议使用单个视频URL")

        # TODO: 实现用户页面视频列表获取
        # 这需要解析用户页面或使用API获取视频列表

    def download_batch(self, urls: List[str], cookies: Dict = None):
        """
        批量下载视频

        Args:
            urls: URL列表
            cookies: Cookie字典
        """
        logger.info(f"批量下载: {len(urls)} 个视频")

        # 批量解析
        results = self.batch_parse(urls, cookies)

        if not results:
            logger.error("批量解析失败")
            return

        # 下载视频
        with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
            futures = []

            for result in results:
                if result.get('success'):
                    video_info = result.get('data')
                    if video_info:
                        future = executor.submit(self.download_video, video_info)
                        futures.append(future)
                else:
                    logger.error(f"解析失败: {result.get('url')} - {result.get('error')}")
                    self.stats['failed'] += 1

            # 等待所有下载完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"下载异常: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 限制长度
        filename = filename[:50]
        # 去除首尾空格
        filename = filename.strip()
        return filename or "untitled"

    def get_stats(self) -> Dict:
        """获取统计信息"""
        # 获取解析服务统计
        try:
            response = self.session.get(f"{self.parsing_service_url}/stats")
            if response.status_code == 200:
                service_stats = response.json()
            else:
                service_stats = {}
        except:
            service_stats = {}

        return {
            'downloader': self.stats,
            'parsing_service': service_stats
        }

    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*50)
        print("📊 下载统计")
        print("="*50)
        print(f"总计: {self.stats['total']}")
        print(f"成功: {self.stats['success']} ✅")
        print(f"失败: {self.stats['failed']} ❌")
        print(f"跳过: {self.stats['skipped']} ⏭️")

        if self.stats['total'] > 0:
            success_rate = self.stats['success'] / self.stats['total'] * 100
            print(f"成功率: {success_rate:.1f}%")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='抖音视频下载器 V3')
    parser.add_argument('urls', nargs='*', help='视频URL（支持多个）')
    parser.add_argument('-s', '--service', default='http://localhost:5000',
                       help='解析服务地址 (默认: http://localhost:5000)')
    parser.add_argument('-o', '--output', default='downloads',
                       help='输出目录 (默认: downloads)')
    parser.add_argument('-c', '--cookies', help='Cookie文件路径')
    parser.add_argument('-m', '--max-workers', type=int, default=5,
                       help='最大并发数 (默认: 5)')
    parser.add_argument('--proxy', action='store_true',
                       help='使用代理')
    parser.add_argument('--force', action='store_true',
                       help='强制刷新（不使用缓存）')
    parser.add_argument('-i', '--interactive', action='store_true',
                       help='交互模式')

    args = parser.parse_args()

    # 创建下载器
    downloader = DouYinDownloaderV3(args.service)

    # 设置输出目录
    downloader.download_dir = Path(args.output)
    downloader.download_dir.mkdir(exist_ok=True)

    # 设置配置
    downloader.config['max_workers'] = args.max_workers
    downloader.config['use_proxy'] = args.proxy
    downloader.config['force_refresh'] = args.force

    # 读取Cookie
    cookies = None
    if args.cookies:
        try:
            cookies = {}
            with open(args.cookies, 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        parts = line.strip().split('\t')
                        if len(parts) >= 7:
                            cookies[parts[5]] = parts[6]
            logger.info(f"已加载 {len(cookies)} 个Cookie")
        except Exception as e:
            logger.error(f"读取Cookie文件失败: {e}")

    # 交互模式
    if args.interactive or not args.urls:
        print("\n" + "="*50)
        print("🎬 抖音视频下载器 V3 - 交互模式")
        print("="*50)
        print("支持的URL格式:")
        print("  - 短链接: https://v.douyin.com/xxxxx/")
        print("  - 视频链接: https://www.douyin.com/video/xxxxx")
        print("  - 用户主页: https://www.douyin.com/user/xxxxx")
        print("\n输入 'q' 退出, 'stats' 查看统计")
        print("-"*50)

        while True:
            try:
                url = input("\n请输入URL: ").strip()

                if url.lower() == 'q':
                    break
                elif url.lower() == 'stats':
                    downloader.print_stats()
                    continue
                elif not url:
                    continue

                # 支持批量输入（空格或逗号分隔）
                urls = re.split(r'[,\s]+', url)

                if len(urls) == 1:
                    downloader.download_from_url(urls[0], cookies)
                else:
                    downloader.download_batch(urls, cookies)

            except KeyboardInterrupt:
                print("\n\n已取消")
                break
            except Exception as e:
                logger.error(f"处理错误: {e}")

    # 批量模式
    elif args.urls:
        if len(args.urls) == 1:
            downloader.download_from_url(args.urls[0], cookies)
        else:
            downloader.download_batch(args.urls, cookies)

    # 打印统计
    downloader.print_stats()


if __name__ == "__main__":
    main()