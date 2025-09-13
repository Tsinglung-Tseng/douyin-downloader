#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
简化版Cookie获取工具
"""

import asyncio
import json
import yaml
import time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ 请先安装Playwright: pip3 install playwright && playwright install chromium")
    exit(1)


async def main():
    print("="*60)
    print("🍪 抖音Cookie获取工具（简化版）")
    print("="*60)
    
    async with async_playwright() as p:
        print("\n📱 启动浏览器...")
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        print("📍 尝试访问抖音...")
        try:
            # 不等待页面完全加载
            await page.goto('https://www.douyin.com', timeout=10000)
        except:
            print("⚠️ 页面加载超时，但继续运行...")
        
        print("\n" + "="*60)
        print("📋 手动操作步骤：")
        print("1. 如果页面未加载，手动输入: www.douyin.com")
        print("2. 点击右上角【登录】")
        print("3. 选择登录方式并完成登录")
        print("4. 看到头像后，按下面的Enter键")
        print("="*60)
        
        # 等待用户输入
        input("\n✋ 完成登录后，按Enter键继续...")
        
        print("\n📡 获取Cookie中...")
        await asyncio.sleep(2)
        
        # 获取cookies
        cookies = await context.cookies()
        
        if cookies:
            print(f"✅ 获取到 {len(cookies)} 个Cookie")
            
            # 转换为字典
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie['name']] = cookie['value']
            
            # 保存到配置
            config_path = Path('config.yml')
            config = {}
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            
            config['cookies'] = cookie_dict
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"✅ Cookie已保存到: {config_path}")
            
            # 保存备份
            with open('cookie.json', 'w', encoding='utf-8') as f:
                json.dump(cookie_dict, f, ensure_ascii=False, indent=2)
            
            print("✅ 备份已保存到: cookie.json")
            
            # 显示关键Cookie
            important = ['msToken', 'ttwid', 'sessionid', 'odin_tt', 'sid_guard']
            print("\n📋 关键Cookie:")
            for key in important:
                if key in cookie_dict:
                    value = cookie_dict[key]
                    if len(value) > 30:
                        print(f"  {key}: {value[:30]}...")
                    else:
                        print(f"  {key}: {value}")
            
            print("\n✅ 完成！现在可以关闭浏览器")
            print("下一步: python3 test_real_video.py")
            
            # 等待一下让用户看到结果
            await asyncio.sleep(5)
        else:
            print("❌ 未获取到Cookie")
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())