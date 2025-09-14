#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
指标收集器
"""

import time
import logging
from typing import Dict, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCollector:
    """指标收集器"""

    def __init__(self, window_size: int = 3600):
        """
        初始化指标收集器

        Args:
            window_size: 时间窗口大小（秒）
        """
        self.window_size = window_size
        self.start_time = time.time()

        # 计数器
        self.counters = defaultdict(int)

        # 时间序列数据
        self.timeseries = defaultdict(lambda: deque(maxlen=1000))

        # 延迟统计
        self.latencies = defaultdict(list)

        # 策略统计
        self.strategy_stats = defaultdict(lambda: {
            'success': 0,
            'failure': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0
        })

    def record_request(self, url_type: str = 'video'):
        """
        记录请求

        Args:
            url_type: URL类型
        """
        self.counters['total_requests'] += 1
        self.counters[f'requests_{url_type}'] += 1

        # 记录时间序列
        self.timeseries['requests'].append({
            'timestamp': time.time(),
            'type': url_type
        })

    def record_parse_success(self, strategy: str, elapsed: float):
        """
        记录解析成功

        Args:
            strategy: 策略名称
            elapsed: 耗时（秒）
        """
        self.counters['total_success'] += 1
        self.counters[f'success_{strategy}'] += 1

        # 更新策略统计
        stats = self.strategy_stats[strategy]
        stats['success'] += 1
        stats['total_time'] += elapsed
        stats['min_time'] = min(stats['min_time'], elapsed)
        stats['max_time'] = max(stats['max_time'], elapsed)

        # 记录延迟
        self.latencies[strategy].append(elapsed)

        # 记录时间序列
        self.timeseries['success'].append({
            'timestamp': time.time(),
            'strategy': strategy,
            'elapsed': elapsed
        })

        logger.info(f"Parse success: {strategy} in {elapsed:.2f}s")

    def record_parse_failure(self, strategy: str = None):
        """
        记录解析失败

        Args:
            strategy: 策略名称
        """
        self.counters['total_failure'] += 1

        if strategy:
            self.counters[f'failure_{strategy}'] += 1
            self.strategy_stats[strategy]['failure'] += 1

        # 记录时间序列
        self.timeseries['failure'].append({
            'timestamp': time.time(),
            'strategy': strategy
        })

        logger.warning(f"Parse failure: {strategy or 'unknown'}")

    def record_cache_hit(self):
        """记录缓存命中"""
        self.counters['cache_hits'] += 1

        self.timeseries['cache'].append({
            'timestamp': time.time(),
            'type': 'hit'
        })

    def record_cache_miss(self):
        """记录缓存未命中"""
        self.counters['cache_misses'] += 1

        self.timeseries['cache'].append({
            'timestamp': time.time(),
            'type': 'miss'
        })

    def record_error(self, error_type: str, error_msg: str):
        """
        记录错误

        Args:
            error_type: 错误类型
            error_msg: 错误消息
        """
        self.counters['total_errors'] += 1
        self.counters[f'error_{error_type}'] += 1

        self.timeseries['errors'].append({
            'timestamp': time.time(),
            'type': error_type,
            'message': error_msg
        })

        logger.error(f"Error [{error_type}]: {error_msg}")

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取指标

        Returns:
            指标字典
        """
        current_time = time.time()
        uptime = current_time - self.start_time

        # 计算成功率
        total_requests = self.counters['total_requests']
        total_success = self.counters['total_success']
        success_rate = total_success / total_requests if total_requests > 0 else 0

        # 计算缓存命中率
        cache_hits = self.counters['cache_hits']
        cache_misses = self.counters['cache_misses']
        cache_total = cache_hits + cache_misses
        cache_hit_rate = cache_hits / cache_total if cache_total > 0 else 0

        # 计算策略性能
        strategy_performance = self._calculate_strategy_performance()

        # 计算时间序列指标
        recent_metrics = self._calculate_recent_metrics()

        return {
            'uptime': self._format_duration(uptime),
            'total_requests': total_requests,
            'total_success': total_success,
            'total_failure': self.counters['total_failure'],
            'total_errors': self.counters['total_errors'],
            'success_rate': f"{success_rate:.2%}",
            'cache_hit_rate': f"{cache_hit_rate:.2%}",
            'requests_per_minute': self._calculate_rate('requests', 60),
            'strategy_performance': strategy_performance,
            'recent_metrics': recent_metrics,
            'latency_stats': self._calculate_latency_stats()
        }

    def _calculate_strategy_performance(self) -> Dict[str, Dict]:
        """
        计算策略性能

        Returns:
            策略性能字典
        """
        performance = {}

        for strategy, stats in self.strategy_stats.items():
            total = stats['success'] + stats['failure']
            if total == 0:
                continue

            success_rate = stats['success'] / total
            avg_time = stats['total_time'] / stats['success'] if stats['success'] > 0 else 0

            performance[strategy] = {
                'success': stats['success'],
                'failure': stats['failure'],
                'success_rate': f"{success_rate:.2%}",
                'avg_time': f"{avg_time:.2f}s",
                'min_time': f"{stats['min_time']:.2f}s" if stats['min_time'] != float('inf') else "N/A",
                'max_time': f"{stats['max_time']:.2f}s"
            }

        return performance

    def _calculate_recent_metrics(self, window: int = 300) -> Dict:
        """
        计算最近的指标（默认5分钟）

        Args:
            window: 时间窗口（秒）

        Returns:
            最近指标字典
        """
        current_time = time.time()
        window_start = current_time - window

        recent = {
            'requests': 0,
            'success': 0,
            'failure': 0,
            'errors': 0
        }

        # 统计最近的请求
        for event in self.timeseries['requests']:
            if event['timestamp'] > window_start:
                recent['requests'] += 1

        # 统计最近的成功
        for event in self.timeseries['success']:
            if event['timestamp'] > window_start:
                recent['success'] += 1

        # 统计最近的失败
        for event in self.timeseries['failure']:
            if event['timestamp'] > window_start:
                recent['failure'] += 1

        # 统计最近的错误
        for event in self.timeseries['errors']:
            if event['timestamp'] > window_start:
                recent['errors'] += 1

        # 计算速率
        recent['requests_per_minute'] = (recent['requests'] / window) * 60
        recent['success_rate'] = f"{recent['success'] / recent['requests']:.2%}" if recent['requests'] > 0 else "N/A"

        return recent

    def _calculate_latency_stats(self) -> Dict:
        """
        计算延迟统计

        Returns:
            延迟统计字典
        """
        all_latencies = []
        for latencies in self.latencies.values():
            all_latencies.extend(latencies)

        if not all_latencies:
            return {
                'avg': "N/A",
                'min': "N/A",
                'max': "N/A",
                'p50': "N/A",
                'p90': "N/A",
                'p99': "N/A"
            }

        all_latencies.sort()
        count = len(all_latencies)

        return {
            'avg': f"{sum(all_latencies) / count:.2f}s",
            'min': f"{all_latencies[0]:.2f}s",
            'max': f"{all_latencies[-1]:.2f}s",
            'p50': f"{all_latencies[int(count * 0.5)]:.2f}s",
            'p90': f"{all_latencies[int(count * 0.9)]:.2f}s",
            'p99': f"{all_latencies[int(count * 0.99)]:.2f}s"
        }

    def _calculate_rate(self, event_type: str, window: int) -> float:
        """
        计算事件速率

        Args:
            event_type: 事件类型
            window: 时间窗口（秒）

        Returns:
            每分钟速率
        """
        current_time = time.time()
        window_start = current_time - window
        count = 0

        for event in self.timeseries[event_type]:
            if event['timestamp'] > window_start:
                count += 1

        return (count / window) * 60

    def _format_duration(self, seconds: float) -> str:
        """
        格式化持续时间

        Args:
            seconds: 秒数

        Returns:
            格式化的时间字符串
        """
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.0f}m"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        else:
            return f"{seconds / 86400:.1f}d"

    def reset(self):
        """重置所有指标"""
        self.counters.clear()
        self.timeseries.clear()
        self.latencies.clear()
        self.strategy_stats.clear()
        self.start_time = time.time()
        logger.info("Metrics reset")

    def export_prometheus(self) -> str:
        """
        导出Prometheus格式的指标

        Returns:
            Prometheus格式的指标字符串
        """
        lines = []

        # 添加注释和类型信息
        lines.append("# HELP douyin_requests_total Total number of requests")
        lines.append("# TYPE douyin_requests_total counter")
        lines.append(f"douyin_requests_total {self.counters['total_requests']}")

        lines.append("# HELP douyin_success_total Total number of successful parses")
        lines.append("# TYPE douyin_success_total counter")
        lines.append(f"douyin_success_total {self.counters['total_success']}")

        lines.append("# HELP douyin_failure_total Total number of failed parses")
        lines.append("# TYPE douyin_failure_total counter")
        lines.append(f"douyin_failure_total {self.counters['total_failure']}")

        # 策略指标
        for strategy, stats in self.strategy_stats.items():
            lines.append(f'douyin_strategy_success{{strategy="{strategy}"}} {stats["success"]}')
            lines.append(f'douyin_strategy_failure{{strategy="{strategy}"}} {stats["failure"]}')

            if stats['success'] > 0:
                avg_time = stats['total_time'] / stats['success']
                lines.append(f'douyin_strategy_latency{{strategy="{strategy}"}} {avg_time}')

        return "\n".join(lines)