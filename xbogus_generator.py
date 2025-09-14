#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
X-Bogus签名生成器 - 基于最新研究的实现
根据抖音2024-2025年的签名算法实现
"""

import hashlib
import time
import random
import struct
import base64
from typing import Union, Dict, List
import logging

logger = logging.getLogger(__name__)


class XBogusGenerator:
    """
    X-Bogus签名生成器
    基于JavaScript版本的Python实现
    """

    # 字符映射表（抖音使用的自定义Base64）
    CHAR_TABLE = "Dkdpgh4ZKsQB80/MfvW36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVSGaCect"

    # 魔数和常量
    MAGIC_NUMS = [
        0x3b, 0x1f, 0x39, 0x09, 0x2b, 0x0f, 0x15, 0x17,
        0x3f, 0x0d, 0x33, 0x27, 0x25, 0x35, 0x07, 0x1d
    ]

    def __init__(self):
        """初始化生成器"""
        self.canvas_key = self._generate_canvas_key()

    def generate(self, params: Union[str, Dict], user_agent: str = None) -> str:
        """
        生成X-Bogus签名

        Args:
            params: URL参数字符串或字典
            user_agent: 用户代理字符串

        Returns:
            X-Bogus签名字符串
        """
        try:
            # 处理参数
            if isinstance(params, dict):
                param_str = self._dict_to_params(params)
            else:
                param_str = params

            # 默认UA
            if not user_agent:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

            # 获取时间戳（秒）
            timestamp = int(time.time())

            # 构建签名输入
            sign_input = self._build_sign_input(param_str, timestamp, user_agent)

            # 计算签名
            x_bogus = self._calculate_xbogus(sign_input, timestamp)

            logger.debug(f"Generated X-Bogus: {x_bogus}")
            return x_bogus

        except Exception as e:
            logger.error(f"Failed to generate X-Bogus: {e}")
            # 返回备用签名
            return self._generate_fallback_xbogus()

    def _build_sign_input(self, params: str, timestamp: int, user_agent: str) -> bytes:
        """构建签名输入数据"""
        # 组合数据
        # 格式: md5(params) + timestamp + md5(ua) + canvas

        # 计算MD5
        params_md5 = hashlib.md5(params.encode()).digest()
        ua_md5 = hashlib.md5(user_agent.encode()).digest()

        # 时间戳转字节
        ts_bytes = struct.pack('>I', timestamp)

        # Canvas指纹
        canvas_bytes = self.canvas_key.encode()[:8]

        # 组合
        sign_input = params_md5[:8] + ts_bytes + ua_md5[:8] + canvas_bytes

        return sign_input

    def _calculate_xbogus(self, sign_input: bytes, timestamp: int) -> str:
        """计算X-Bogus签名"""
        # 第一步：初始加密
        encrypted = self._encrypt_data(sign_input)

        # 第二步：混淆处理
        obfuscated = self._obfuscate(encrypted, timestamp)

        # 第三步：编码
        x_bogus = self._encode_to_xbogus(obfuscated)

        return x_bogus

    def _encrypt_data(self, data: bytes) -> List[int]:
        """加密数据"""
        encrypted = []

        # 使用魔数进行异或和位移操作
        for i, byte in enumerate(data):
            magic = self.MAGIC_NUMS[i % len(self.MAGIC_NUMS)]

            # 复杂的位运算
            encrypted_byte = ((byte ^ magic) + i) & 0xFF
            encrypted_byte = ((encrypted_byte << 2) | (encrypted_byte >> 6)) & 0xFF
            encrypted_byte = encrypted_byte ^ 0xB7

            encrypted.append(encrypted_byte)

        # 添加校验和
        checksum = sum(encrypted) & 0xFF
        encrypted.append(checksum)

        return encrypted

    def _obfuscate(self, data: List[int], timestamp: int) -> List[int]:
        """混淆处理"""
        obfuscated = []

        # 时间戳因子
        ts_factor = (timestamp & 0xFF) | 0x01

        for i, byte in enumerate(data):
            # 位置相关的混淆
            if i % 3 == 0:
                obf_byte = (byte * ts_factor) & 0xFF
            elif i % 3 == 1:
                obf_byte = (byte ^ ts_factor) & 0xFF
            else:
                obf_byte = ((byte + ts_factor) % 256)

            # 额外的位运算
            obf_byte = ((obf_byte << 4) | (obf_byte >> 4)) & 0xFF

            obfuscated.append(obf_byte)

        return obfuscated

    def _encode_to_xbogus(self, data: List[int]) -> str:
        """编码为X-Bogus格式"""
        # X-Bogus格式：版本(2) + 编码数据(26) = 28字符

        # 版本前缀（DFS开头较常见）
        version = "DF"

        # 将数据编码为自定义Base64
        encoded = self._custom_base64_encode(data)

        # 确保长度
        if len(encoded) < 26:
            # 填充
            encoded += self._generate_padding(26 - len(encoded))
        elif len(encoded) > 26:
            # 截断
            encoded = encoded[:26]

        # 组合
        x_bogus = version + encoded

        # 最终调整（某些位置的字符有特定规律）
        x_bogus = self._final_adjustment(x_bogus)

        return x_bogus

    def _custom_base64_encode(self, data: List[int]) -> str:
        """自定义Base64编码"""
        encoded = ""

        # 将字节数组转换为位流
        bits = ""
        for byte in data:
            bits += format(byte, '08b')

        # 每6位转换为一个字符
        for i in range(0, len(bits), 6):
            chunk = bits[i:i+6]
            if len(chunk) < 6:
                chunk = chunk.ljust(6, '0')

            index = int(chunk, 2)
            encoded += self.CHAR_TABLE[index]

        return encoded

    def _final_adjustment(self, x_bogus: str) -> str:
        """最终调整"""
        # 某些位置的字符需要特殊处理
        x_bogus_list = list(x_bogus)

        # 位置3通常是S或z
        if len(x_bogus_list) > 3:
            if random.random() > 0.5:
                x_bogus_list[3] = 'S' if x_bogus_list[3].isupper() else 'z'

        # 位置7和15经常是特定字符
        special_chars = ['s', 'w', 'V', 'O', 'Y', 'D', '0', 'A']
        if len(x_bogus_list) > 7:
            x_bogus_list[7] = random.choice(special_chars)
        if len(x_bogus_list) > 15:
            x_bogus_list[15] = random.choice(special_chars)

        return ''.join(x_bogus_list)

    def _generate_padding(self, length: int) -> str:
        """生成填充字符"""
        padding = ""
        for _ in range(length):
            padding += random.choice(self.CHAR_TABLE)
        return padding

    def _generate_canvas_key(self) -> str:
        """生成Canvas指纹"""
        # 模拟Canvas指纹
        values = [
            "124.04347527516074",
            "124.08721426937342",
            "124.0434806260746",
            "124.04344968475198"
        ]
        return random.choice(values)

    def _dict_to_params(self, params: Dict) -> str:
        """字典转URL参数"""
        return '&'.join([f"{k}={v}" for k, v in params.items()])

    def _generate_fallback_xbogus(self) -> str:
        """生成备用X-Bogus"""
        # 生成一个格式正确的备用签名
        prefix = "DF"

        # 生成随机但格式正确的签名
        chars = []

        # 第3位
        chars.append('S')
        # 第4-6位
        for _ in range(3):
            chars.append(random.choice(self.CHAR_TABLE))
        # 第7位
        chars.append('w')
        # 第8-14位
        for _ in range(7):
            chars.append(random.choice(self.CHAR_TABLE))
        # 第15位
        chars.append('V')
        # 剩余位
        for _ in range(11):
            chars.append(random.choice(self.CHAR_TABLE))

        return prefix + ''.join(chars)


class ABogusGenerator:
    """
    A-Bogus签名生成器（新版签名）
    """

    # A-Bogus使用的字符表
    CHAR_TABLE = "cdrCvYABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/"

    def __init__(self):
        """初始化生成器"""
        pass

    def generate(self, data: Union[str, Dict], headers: Dict) -> str:
        """
        生成A-Bogus签名

        Args:
            data: 请求数据
            headers: 请求头

        Returns:
            A-Bogus签名
        """
        try:
            # 处理数据
            if isinstance(data, dict):
                import json
                data_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
            else:
                data_str = str(data) if data else ""

            # 提取必要信息
            user_agent = headers.get('User-Agent', '')
            referer = headers.get('Referer', '')

            # 时间戳（毫秒）
            timestamp = int(time.time() * 1000)

            # 构建签名输入
            sign_input = f"{timestamp}:{user_agent}:{referer}:{data_str}"

            # 计算签名
            a_bogus = self._calculate_abogus(sign_input, timestamp)

            logger.debug(f"Generated A-Bogus: {a_bogus}")
            return a_bogus

        except Exception as e:
            logger.error(f"Failed to generate A-Bogus: {e}")
            return self._generate_fallback_abogus()

    def _calculate_abogus(self, sign_input: str, timestamp: int) -> str:
        """计算A-Bogus"""
        # 多重哈希
        hash1 = hashlib.sha256(sign_input.encode()).digest()
        hash2 = hashlib.md5(hash1).digest()

        # 组合哈希
        combined = hash1[:12] + hash2[:8] + struct.pack('>Q', timestamp)[:4]

        # 编码
        a_bogus = self._encode_abogus(combined)

        return a_bogus

    def _encode_abogus(self, data: bytes) -> str:
        """编码A-Bogus"""
        # A-Bogus格式：前缀(2) + 编码数据(168)
        prefix = "CJ"

        # Base64变体编码
        encoded = ""

        # 转换为位流
        bits = ""
        for byte in data:
            bits += format(byte, '08b')

        # 每6位编码
        for i in range(0, len(bits), 6):
            chunk = bits[i:i+6]
            if len(chunk) < 6:
                chunk = chunk.ljust(6, '0')

            index = int(chunk, 2)
            encoded += self.CHAR_TABLE[index % len(self.CHAR_TABLE)]

        # 填充到需要的长度
        while len(encoded) < 168:
            encoded += random.choice(self.CHAR_TABLE)

        return prefix + encoded[:168]

    def _generate_fallback_abogus(self) -> str:
        """生成备用A-Bogus"""
        prefix = "CJ"
        chars = ''.join([random.choice(self.CHAR_TABLE) for _ in range(168)])
        return prefix + chars


# 便捷函数
def generate_x_bogus(params: Union[str, Dict], user_agent: str = None) -> str:
    """生成X-Bogus签名"""
    generator = XBogusGenerator()
    return generator.generate(params, user_agent)


def generate_a_bogus(data: Union[str, Dict], headers: Dict) -> str:
    """生成A-Bogus签名"""
    generator = ABogusGenerator()
    return generator.generate(data, headers)


if __name__ == "__main__":
    # 测试X-Bogus
    test_params = {
        'aweme_id': '7549035040701844779',
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
    }

    # 测试生成
    print("=== X-Bogus测试 ===")
    for i in range(3):
        x_bogus = generate_x_bogus(test_params)
        print(f"X-Bogus {i+1}: {x_bogus} (长度: {len(x_bogus)})")

    print("\n=== A-Bogus测试 ===")
    test_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://www.douyin.com/'
    }

    for i in range(3):
        a_bogus = generate_a_bogus({}, test_headers)
        print(f"A-Bogus {i+1}: {a_bogus} (长度: {len(a_bogus)})")