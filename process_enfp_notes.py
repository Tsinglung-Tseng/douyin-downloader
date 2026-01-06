import os
import json
import re
from datetime import datetime

# Configuration
SOURCE_DIR = "/Users/tsinglungtseng/scaffold/douyin-downloader/Downloaded/user_粽子MBTI_MS4wLjABAAAAl-44wp7rPDn_qr3RAetfNfkVbmxKkDlaS4QHmrztFnSatiqSfbwuZVX1i2bE7JiY/post"
TARGET_DIR = "/Users/tsinglungtseng/obsidian/RPG"
TAG_FILTER = "ENFP"

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def process():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)

    for subdir in os.listdir(SOURCE_DIR):
        path = os.path.join(SOURCE_DIR, subdir)
        if not os.path.isdir(path):
            continue

        files = os.listdir(path)
        result_file = next((f for f in files if f.endswith("_result.json")), None)
        transcript_file = "transcript.json" if "transcript.json" in files else None

        if not result_file or not transcript_file:
            continue

        try:
            with open(os.path.join(path, result_file), 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Error reading {result_file} in {subdir}: {e}")
            continue
        
        desc = metadata.get("desc", "")
        if TAG_FILTER.lower() not in desc.lower():
            continue

        try:
            with open(os.path.join(path, transcript_file), 'r', encoding='utf-8') as f:
                transcript_data = json.load(f)
        except Exception as e:
            print(f"Error reading {transcript_file} in {subdir}: {e}")
            continue
        
        content_text = transcript_data.get("text", "")
        if not content_text or content_text.strip().lower() == "you": # Skip empty/invalid transcripts
            continue

        # Extract Title
        title_lines = desc.split('\n')
        title = title_lines[0].strip() if title_lines else subdir
        if not title or title.startswith("#"):
            title = subdir
        
        # Clean title for filename (remove tags)
        clean_title = re.sub(r'#\w+', '', title).strip()
        if not clean_title:
            clean_title = subdir
            
        filename = sanitize_filename(clean_title) + ".md"
        target_path = os.path.join(TARGET_DIR, filename)

        # Build YAML Properties
        create_time = metadata.get("create_time", "")
        author = metadata.get("author", {}).get("nickname", "粽子MBTI")
        aweme_id = metadata.get("aweme_id", "")
        tags = re.findall(r'#(\w+)', desc)
        
        aliases = [clean_title]
        # Add some aliases based on tags and keywords
        if "ENFP" in [t.upper() for t in tags]: aliases.append("快乐小狗")
        aliases.extend(tags[:3])
        aliases = list(set(aliases))

        yaml_content = f"""---
property: true
title: "{clean_title}"
create_time: {create_time}
author: "{author}"
source: "Douyin"
aweme_id: "{aweme_id}"
type: "Video Note"
tags: {json.dumps(tags, ensure_ascii=False)}
aliases: {json.dumps(aliases, ensure_ascii=False)}
---
"""

        # Build Body
        body_content = f"""
# {clean_title}

## 视频描述 (Description)
{desc}

## 转录内容 (Transcript)
{content_text}

---
> [!NOTE]
> 笔记由 Antigravity 自动生成，基于视频元数据和语音转路稿。
"""

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content + body_content)
        
        print(f"Generated: {filename}")

if __name__ == "__main__":
    process()
