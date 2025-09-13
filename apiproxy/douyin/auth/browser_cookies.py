#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器Cookie提取器 - 完全按照yt-dlp的实现方式
支持从Chrome、Edge、Firefox等浏览器直接提取Cookie
包含完整的解密功能
"""

import os
import json
import sqlite3
import platform
import tempfile
import shutil
import base64
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote
import logging

logger = logging.getLogger(__name__)

# 尝试导入加密库
try:
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("pycryptodome未安装，Cookie解密功能受限")

class BrowserCookieExtractor:
    """
    浏览器Cookie提取器
    完全模仿yt-dlp的实现方式
    """

    def __init__(self):
        self.system = platform.system()
        self._chrome_key_cache = {}

    def get_cookies_from_browser(self, browser: str = 'chrome', domain: str = '.douyin.com') -> Dict[str, str]:
        """
        主入口函数 - 从指定浏览器获取Cookie
        返回格式：{name: value}

        Args:
            browser: 浏览器名称 (chrome/edge/firefox/safari)
            domain: 要提取的域名
        """
        logger.info(f"从{browser}提取{domain}的Cookie...")

        if browser in ['chrome', 'chromium', 'edge', 'brave', 'opera', 'vivaldi']:
            cookies = self._extract_chrome_cookies(browser, domain)
        elif browser == 'firefox':
            cookies = self._extract_firefox_cookies(domain)
        elif browser == 'safari':
            cookies = self._extract_safari_cookies(domain)
        else:
            raise ValueError(f"不支持的浏览器: {browser}")

        # 转换为字典格式
        cookie_dict = {}
        for cookie in cookies:
            if cookie.get('value'):
                cookie_dict[cookie['name']] = cookie['value']

        # 记录关键Cookie
        if 'msToken' in cookie_dict:
            logger.info(f"✅ 找到msToken: {cookie_dict['msToken'][:30]}...")
        if 'ttwid' in cookie_dict:
            logger.info(f"✅ 找到ttwid: {cookie_dict['ttwid'][:30]}...")
        if 'sessionid' in cookie_dict:
            logger.info(f"✅ 找到sessionid: {cookie_dict['sessionid'][:20]}...")

        return cookie_dict

    def _extract_chrome_cookies(self, browser: str, domain: str) -> List[Dict]:
        """
        从Chrome系浏览器提取Cookie（包含解密）
        这是yt-dlp的核心实现
        """
        cookie_file = self._get_chrome_cookie_path(browser)
        if not cookie_file or not cookie_file.exists():
            raise FileNotFoundError(f"找不到{browser}的Cookie文件")

        logger.info(f"Cookie文件: {cookie_file}")

        # 创建临时副本
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()

        try:
            shutil.copy2(cookie_file, temp_file.name)

            # 获取解密密钥
            decryption_key = self._get_chrome_key(browser)

            # 连接数据库
            conn = sqlite3.connect(temp_file.name)
            cursor = conn.cursor()

            # 查询Cookie
            query = """
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly
                FROM cookies
                WHERE host_key LIKE ?
                ORDER BY host_key
            """

            cursor.execute(query, (f'%{domain}%',))
            cookies = []

            for row in cursor.fetchall():
                host_key = row[0]
                name = row[1]
                value = row[2]
                encrypted_value = row[3]
                path = row[4]
                expires = row[5]
                secure = bool(row[6])
                httponly = bool(row[7])

                # 解密Cookie值
                if value:
                    decrypted_value = value
                elif encrypted_value:
                    decrypted_value = self._decrypt_chrome_cookie(
                        encrypted_value, decryption_key
                    )
                else:
                    decrypted_value = ''

                if decrypted_value:
                    cookies.append({
                        'domain': host_key,
                        'name': name,
                        'value': decrypted_value,
                        'path': path,
                        'expires': expires,
                        'secure': secure,
                        'httpOnly': httponly
                    })

            conn.close()
            return cookies

        finally:
            os.unlink(temp_file.name)

    def _get_chrome_cookie_path(self, browser: str) -> Optional[Path]:
        """获取Chrome系浏览器的Cookie文件路径"""
        home = Path.home()

        paths = {
            'Darwin': {  # macOS
                'chrome': home / 'Library/Application Support/Google/Chrome/Default/Cookies',
                'chromium': home / 'Library/Application Support/Chromium/Default/Cookies',
                'edge': home / 'Library/Application Support/Microsoft Edge/Default/Cookies',
                'brave': home / 'Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies',
                'opera': home / 'Library/Application Support/com.operasoftware.Opera/Cookies',
                'vivaldi': home / 'Library/Application Support/Vivaldi/Default/Cookies',
            },
            'Windows': {
                'chrome': Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/User Data/Default/Network/Cookies',
                'chromium': Path(os.environ.get('LOCALAPPDATA', '')) / 'Chromium/User Data/Default/Network/Cookies',
                'edge': Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/Edge/User Data/Default/Network/Cookies',
                'brave': Path(os.environ.get('LOCALAPPDATA', '')) / 'BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies',
            },
            'Linux': {
                'chrome': home / '.config/google-chrome/Default/Cookies',
                'chromium': home / '.config/chromium/Default/Cookies',
                'brave': home / '.config/BraveSoftware/Brave-Browser/Default/Cookies',
            }
        }

        system_paths = paths.get(self.system, {})
        cookie_path = system_paths.get(browser)

        # 尝试新旧版本路径
        if cookie_path and not cookie_path.exists():
            # Chrome 96+ 将Cookies移到了Network子目录
            if 'Network' not in str(cookie_path):
                network_path = cookie_path.parent / 'Network' / 'Cookies'
                if network_path.exists():
                    return network_path

        return cookie_path

    def _get_chrome_key(self, browser: str) -> Optional[bytes]:
        """
        获取Chrome的解密密钥
        这是yt-dlp的核心功能之一
        """
        if browser in self._chrome_key_cache:
            return self._chrome_key_cache[browser]

        key = None

        if self.system == 'Darwin':  # macOS
            # 使用security命令从Keychain获取
            try:
                # Chrome的密钥存储在Keychain中
                service_name = {
                    'chrome': 'Chrome',
                    'chromium': 'Chromium',
                    'edge': 'Microsoft Edge',
                    'brave': 'Brave',
                    'opera': 'Opera',
                    'vivaldi': 'Vivaldi'
                }.get(browser, 'Chrome')

                cmd = [
                    'security', 'find-generic-password',
                    '-w',  # 只输出密码
                    '-s', f'{service_name} Safe Storage',
                    '-a', service_name
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    password = result.stdout.strip()
                    # 使用PBKDF2生成密钥
                    if HAS_CRYPTO:
                        key = PBKDF2(password.encode(), b'saltysalt', 16, 1003)
                    else:
                        logger.warning("需要pycryptodome库来生成解密密钥")

            except Exception as e:
                logger.error(f"获取Keychain密钥失败: {e}")

        elif self.system == 'Windows':
            # Windows使用DPAPI，密钥在Local State文件中
            try:
                local_state_path = self._get_chrome_local_state_path(browser)
                if local_state_path and local_state_path.exists():
                    with open(local_state_path, 'r') as f:
                        local_state = json.load(f)
                    encrypted_key = base64.b64decode(
                        local_state['os_crypt']['encrypted_key']
                    )
                    # 移除DPAPI前缀
                    encrypted_key = encrypted_key[5:]
                    # Windows需要使用win32crypt解密
                    try:
                        import win32crypt
                        key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                    except ImportError:
                        logger.warning("需要pywin32库来解密Windows Cookie")

            except Exception as e:
                logger.error(f"获取Windows密钥失败: {e}")

        elif self.system == 'Linux':
            # Linux默认使用固定密钥或gnome-keyring
            key = b'peanuts'  # Chrome默认密钥

        self._chrome_key_cache[browser] = key
        return key

    def _get_chrome_local_state_path(self, browser: str) -> Optional[Path]:
        """获取Chrome的Local State文件路径（Windows）"""
        if self.system != 'Windows':
            return None

        local = Path(os.environ.get('LOCALAPPDATA', ''))
        paths = {
            'chrome': local / 'Google/Chrome/User Data/Local State',
            'edge': local / 'Microsoft/Edge/User Data/Local State',
            'brave': local / 'BraveSoftware/Brave-Browser/User Data/Local State',
        }

        return paths.get(browser)

    def _decrypt_chrome_cookie(self, encrypted_value: bytes, key: Optional[bytes]) -> str:
        """
        解密Chrome Cookie
        完全按照yt-dlp的实现
        """
        if not encrypted_value:
            return ''

        # 检查是否是加密的值
        if encrypted_value[:3] == b'v10':
            # Chrome 80+ 使用AES-GCM加密
            if not key or not HAS_CRYPTO:
                return '[需要解密]'

            try:
                # v10格式：3字节前缀 + 12字节nonce + 密文 + 16字节tag
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:-16]
                tag = encrypted_value[-16:]

                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                plaintext = cipher.decrypt_and_verify(ciphertext, tag)
                return plaintext.decode('utf-8', errors='ignore')

            except Exception as e:
                logger.error(f"解密失败: {e}")
                return '[解密失败]'

        elif encrypted_value[:3] == b'v11':
            # Chrome Windows v11格式
            return self._decrypt_chrome_cookie(b'v10' + encrypted_value[3:], key)

        else:
            # 未加密或旧版本
            try:
                return encrypted_value.decode('utf-8', errors='ignore')
            except:
                return ''

    def _extract_firefox_cookies(self, domain: str) -> List[Dict]:
        """从Firefox提取Cookie"""
        profile_dir = self._get_firefox_profile()
        if not profile_dir:
            raise FileNotFoundError("找不到Firefox配置文件")

        cookie_file = profile_dir / 'cookies.sqlite'
        if not cookie_file.exists():
            raise FileNotFoundError(f"找不到Firefox Cookie文件: {cookie_file}")

        conn = sqlite3.connect(str(cookie_file))
        cursor = conn.cursor()

        query = """
            SELECT host, name, value, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies
            WHERE host LIKE ?
        """

        cursor.execute(query, (f'%{domain}%',))
        cookies = []

        for row in cursor.fetchall():
            cookies.append({
                'domain': row[0],
                'name': row[1],
                'value': row[2],
                'path': row[3],
                'expires': row[4],
                'secure': bool(row[5]),
                'httpOnly': bool(row[6])
            })

        conn.close()
        return cookies

    def _get_firefox_profile(self) -> Optional[Path]:
        """获取Firefox默认配置文件路径"""
        home = Path.home()

        if self.system == 'Darwin':
            base = home / 'Library/Application Support/Firefox/Profiles'
        elif self.system == 'Windows':
            base = Path(os.environ.get('APPDATA', '')) / 'Mozilla/Firefox/Profiles'
        else:  # Linux
            base = home / '.mozilla/firefox'

        if not base.exists():
            return None

        # 查找默认配置文件
        for profile in base.glob('*.default*'):
            if profile.is_dir():
                return profile

        return None

    def _extract_safari_cookies(self, domain: str) -> List[Dict]:
        """从Safari提取Cookie（仅macOS）"""
        if self.system != 'Darwin':
            raise NotImplementedError("Safari仅在macOS上可用")

        # Safari的Cookie存储在二进制plist文件中
        cookie_file = Path.home() / 'Library/Cookies/Cookies.binarycookies'

        if not cookie_file.exists():
            raise FileNotFoundError(f"找不到Safari Cookie文件: {cookie_file}")

        # Safari Cookie需要特殊处理
        # 这里简化处理，实际需要解析二进制格式
        logger.warning("Safari Cookie提取需要额外实现")
        return []

    def to_netscape_format(self, cookies: Dict[str, str], domain: str = '.douyin.com') -> str:
        """
        将Cookie字典转换为Netscape格式字符串
        用于兼容yt-dlp和wget等工具
        """
        lines = [
            "# Netscape HTTP Cookie File",
            "# This file is compatible with yt-dlp --cookies option",
            ""
        ]

        for name, value in cookies.items():
            # 格式：domain flag path secure expiry name value
            line = f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}"
            lines.append(line)

        return '\n'.join(lines)


def get_browser_cookies(browser: str = 'chrome', domain: str = '.douyin.com') -> Dict[str, str]:
    """
    便捷函数 - 获取浏览器Cookie

    Args:
        browser: 浏览器名称
        domain: 域名

    Returns:
        Cookie字典 {name: value}
    """
    extractor = BrowserCookieExtractor()
    return extractor.get_cookies_from_browser(browser, domain)


def save_cookies_to_file(cookies: Dict[str, str], filename: str = 'cookies_browser.txt'):
    """保存Cookie到文件（Netscape格式）"""
    extractor = BrowserCookieExtractor()
    content = extractor.to_netscape_format(cookies)

    with open(filename, 'w') as f:
        f.write(content)

    logger.info(f"Cookie已保存到: {filename}")


if __name__ == "__main__":
    # 测试代码
    import sys
    logging.basicConfig(level=logging.INFO)

    browser = sys.argv[1] if len(sys.argv) > 1 else 'chrome'

    try:
        cookies = get_browser_cookies(browser)

        print(f"\n从{browser}提取到 {len(cookies)} 个Cookie")

        # 显示关键Cookie
        for key in ['msToken', 'ttwid', 'sessionid', 'sid_guard']:
            if key in cookies:
                value = cookies[key]
                display = value[:30] + '...' if len(value) > 30 else value
                print(f"  ✅ {key}: {display}")
            else:
                print(f"  ❌ {key}: 未找到")

        # 保存到文件
        save_cookies_to_file(cookies)

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)