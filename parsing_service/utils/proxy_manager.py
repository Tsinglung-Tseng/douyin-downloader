#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
代理管理器
"""

import random
import time
import logging
import asyncio
import aiohttp
from typing import Optional, List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class ProxyManager:
    """代理管理器"""

    def __init__(self, proxies: List[str] = None):
        """
        初始化代理管理器

        Args:
            proxies: 代理列表
        """
        self.proxies = proxies or []
        self.proxy_stats = defaultdict(lambda: {
            'success': 0,
            'failure': 0,
            'last_used': 0,
            'last_success': 0,
            'blocked': False,
            'block_until': 0
        })
        self.test_url = "https://www.douyin.com"
        self.rotation_strategy = 'random'  # random, round-robin, weighted
        self.current_index = 0

    def add_proxy(self, proxy: str):
        """
        添加代理

        Args:
            proxy: 代理地址 (http://ip:port 或 http://user:pass@ip:port)
        """
        if proxy not in self.proxies:
            self.proxies.append(proxy)
            logger.info(f"Added proxy: {self._mask_proxy(proxy)}")

    def remove_proxy(self, proxy: str):
        """
        移除代理

        Args:
            proxy: 代理地址
        """
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            logger.info(f"Removed proxy: {self._mask_proxy(proxy)}")

    def get_proxy(self, strategy: str = None) -> Optional[str]:
        """
        获取代理

        Args:
            strategy: 策略 (random, round-robin, weighted)

        Returns:
            代理地址
        """
        if not self.proxies:
            return None

        strategy = strategy or self.rotation_strategy
        available_proxies = self._get_available_proxies()

        if not available_proxies:
            logger.warning("No available proxies")
            return None

        if strategy == 'random':
            proxy = random.choice(available_proxies)
        elif strategy == 'round-robin':
            proxy = available_proxies[self.current_index % len(available_proxies)]
            self.current_index += 1
        elif strategy == 'weighted':
            proxy = self._get_weighted_proxy(available_proxies)
        else:
            proxy = available_proxies[0]

        # 更新使用时间
        self.proxy_stats[proxy]['last_used'] = time.time()
        logger.debug(f"Selected proxy: {self._mask_proxy(proxy)}")

        return proxy

    def _get_available_proxies(self) -> List[str]:
        """
        获取可用代理列表

        Returns:
            可用代理列表
        """
        available = []
        current_time = time.time()

        for proxy in self.proxies:
            stats = self.proxy_stats[proxy]

            # 检查是否被禁用
            if stats['blocked']:
                if current_time < stats['block_until']:
                    continue
                else:
                    # 解除禁用
                    stats['blocked'] = False
                    stats['block_until'] = 0

            # 检查冷却时间（避免过度使用）
            if current_time - stats['last_used'] < 1:  # 1秒冷却
                continue

            available.append(proxy)

        return available

    def _get_weighted_proxy(self, proxies: List[str]) -> str:
        """
        根据成功率加权选择代理

        Args:
            proxies: 代理列表

        Returns:
            选中的代理
        """
        weights = []

        for proxy in proxies:
            stats = self.proxy_stats[proxy]
            total = stats['success'] + stats['failure']

            if total == 0:
                # 新代理，给予中等权重
                weight = 0.5
            else:
                # 根据成功率计算权重
                success_rate = stats['success'] / total
                weight = success_rate

            weights.append(weight)

        # 加权随机选择
        if sum(weights) == 0:
            return random.choice(proxies)

        return random.choices(proxies, weights=weights)[0]

    def mark_success(self, proxy: str):
        """
        标记代理成功

        Args:
            proxy: 代理地址
        """
        if proxy:
            self.proxy_stats[proxy]['success'] += 1
            self.proxy_stats[proxy]['last_success'] = time.time()
            logger.debug(f"Proxy success: {self._mask_proxy(proxy)}")

    def mark_failure(self, proxy: str, block_duration: int = 300):
        """
        标记代理失败

        Args:
            proxy: 代理地址
            block_duration: 禁用时间（秒）
        """
        if proxy:
            stats = self.proxy_stats[proxy]
            stats['failure'] += 1

            # 连续失败3次，暂时禁用
            recent_failures = self._count_recent_failures(proxy)
            if recent_failures >= 3:
                stats['blocked'] = True
                stats['block_until'] = time.time() + block_duration
                logger.warning(f"Proxy blocked for {block_duration}s: {self._mask_proxy(proxy)}")
            else:
                logger.debug(f"Proxy failure ({recent_failures}/3): {self._mask_proxy(proxy)}")

    def _count_recent_failures(self, proxy: str, window: int = 60) -> int:
        """
        统计最近的失败次数

        Args:
            proxy: 代理地址
            window: 时间窗口（秒）

        Returns:
            失败次数
        """
        stats = self.proxy_stats[proxy]
        current_time = time.time()

        # 简化实现：如果最近成功过，重置计数
        if stats['last_success'] > current_time - window:
            return 1

        # 否则返回连续失败次数的估计
        return min(stats['failure'], 3)

    async def test_proxy(self, proxy: str) -> bool:
        """
        测试代理是否可用

        Args:
            proxy: 代理地址

        Returns:
            是否可用
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.test_url,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.mark_success(proxy)
                        return True
                    else:
                        self.mark_failure(proxy)
                        return False

        except Exception as e:
            logger.error(f"Proxy test failed: {self._mask_proxy(proxy)} - {e}")
            self.mark_failure(proxy)
            return False

    async def test_all_proxies(self) -> Dict[str, bool]:
        """
        测试所有代理

        Returns:
            测试结果
        """
        results = {}
        tasks = []

        for proxy in self.proxies:
            tasks.append(self.test_proxy(proxy))

        test_results = await asyncio.gather(*tasks, return_exceptions=True)

        for proxy, result in zip(self.proxies, test_results):
            if isinstance(result, Exception):
                results[proxy] = False
            else:
                results[proxy] = result

        return results

    def get_stats(self) -> Dict:
        """
        获取代理统计

        Returns:
            统计信息
        """
        total_proxies = len(self.proxies)
        available_proxies = len(self._get_available_proxies())
        blocked_proxies = sum(1 for p in self.proxies if self.proxy_stats[p]['blocked'])

        total_success = sum(self.proxy_stats[p]['success'] for p in self.proxies)
        total_failure = sum(self.proxy_stats[p]['failure'] for p in self.proxies)
        total_requests = total_success + total_failure

        return {
            'total_proxies': total_proxies,
            'available_proxies': available_proxies,
            'blocked_proxies': blocked_proxies,
            'total_requests': total_requests,
            'total_success': total_success,
            'total_failure': total_failure,
            'success_rate': f"{total_success / total_requests:.2%}" if total_requests > 0 else "0%",
            'proxy_details': self._get_proxy_details()
        }

    def _get_proxy_details(self) -> List[Dict]:
        """
        获取代理详细信息

        Returns:
            代理详细信息列表
        """
        details = []

        for proxy in self.proxies:
            stats = self.proxy_stats[proxy]
            total = stats['success'] + stats['failure']

            details.append({
                'proxy': self._mask_proxy(proxy),
                'success': stats['success'],
                'failure': stats['failure'],
                'success_rate': f"{stats['success'] / total:.2%}" if total > 0 else "N/A",
                'blocked': stats['blocked'],
                'last_used': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats['last_used'])) if stats['last_used'] else 'Never'
            })

        return details

    def _mask_proxy(self, proxy: str) -> str:
        """
        遮罩代理敏感信息

        Args:
            proxy: 代理地址

        Returns:
            遮罩后的代理地址
        """
        if '@' in proxy:
            # 隐藏用户名密码
            parts = proxy.split('@')
            return f"http://***:***@{parts[1]}"
        else:
            # 部分隐藏IP
            import re
            return re.sub(r'(\d+\.\d+)\.\d+\.\d+', r'\1.*.*', proxy)

    def load_from_file(self, filepath: str):
        """
        从文件加载代理

        Args:
            filepath: 文件路径
        """
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.add_proxy(line)

            logger.info(f"Loaded {len(self.proxies)} proxies from {filepath}")

        except Exception as e:
            logger.error(f"Failed to load proxies from file: {e}")