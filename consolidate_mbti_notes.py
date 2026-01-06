
import os
import re

TARGET_DIR = '/Users/tsinglungtseng/obsidian/RPG'

def get_base_name(filename):
    name = filename.replace('.md', '')
    name = name.replace('分析', '')
    name = name.replace('（不破防）', '')
    name = name.replace(' (INTJ、INFJ）', '')
    name = name.strip()
    # Normalize common variations
    if 'INTJ眼神' in name:
        return 'INTJ眼神的压迫感'
    if 'MBTI16人格夸夸' in name:
        return 'MBTI16人格夸夸'
    return name

def merge_files():
    all_files = [f for f in os.listdir(TARGET_DIR) if f.endswith('.md')]
    mbti_keywords = ['MBTI', 'ENFP', 'ENTP', 'INTJ', 'INFJ', '人格', '绿人组', 'P人', 'J人']
    mbti_files = [f for f in all_files if any(k in f.upper() for k in mbti_keywords)]
    
    groups = {}
    for f in mbti_files:
        base = get_base_name(f)
        if base not in groups:
            groups[base] = []
        groups[base].append(f)
    
    for base, files in groups.items():
        print(f"Processing group: {base} -> {files}")
        
        # Determine target file name
        target_file = os.path.join(TARGET_DIR, base + '.md')
        
        # Store components
        frontmatter = ""
        desc = ""
        transcript = ""
        summary = ""
        insights = ""
        mermaid = ""
        
        raw_contents = []
        for f in files:
            with open(os.path.join(TARGET_DIR, f), 'r') as file:
                content = file.read()
                raw_contents.append(content)
        
        # Pick frontmatter from the most complete looking one
        for content in sorted(raw_contents, key=len, reverse=True):
            match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            if match:
                frontmatter = match.group(1)
                break
        
        # Extract sections from all contents
        for content in raw_contents:
            # Desc
            match = re.search(r'## (视频描述|视频/内容描述) \(Description\)\n(.*?)(?=\n##|---|$)', content, re.DOTALL)
            if match: desc = match.group(2).strip()
            
            # Transcript
            match = re.search(r'## (转录内容|转录文本|语音转录) \(Transcript\)\n(.*?)(?=\n##|---|Analysis Section:|$)', content, re.DOTALL)
            if match: transcript = match.group(2).strip()
            
            # Summary
            match = re.search(r'## (核心摘要|摘要分析) \(Core Summary\)\n(.*?)(?=\n##|---|$)', content, re.DOTALL)
            if match: summary = match.group(2).strip()
            
            # Insights
            match = re.search(r'## (深度见解|性格见解|人格见解|分析建议|机制解析|竞争力基因分析|理由分析) \(Deep Insights\)\n(.*?)(?=\n##|---|$)', content, re.DOTALL)
            if match: insights = match.group(2).strip()
            # If not found with Deep Insights tag, try other analysis headers
            if not insights:
                alt_headers = ['## 表象与本质 (Surface vs Core)', '## 脾气爆发逻辑 (Logic of Outburst)', '## 所谓的“双标”真相 (The Truth of Subjectivity)', '## 竞争力基因分析 (Analysis of Competitiveness)', '## 机制解析 (Mechanism Analysis)']
                for header in alt_headers:
                    match = re.search(re.escape(header) + r'\n(.*?)(?=\n##|---|$)', content, re.DOTALL)
                    if match:
                        insights += f"\n\n### {header}\n{match.group(1).strip()}"
                insights = insights.strip()
            
            # Mermaid
            match = re.search(r'## (逻辑映射|心理剖析|记忆冲突图|心理演变逻辑|学术成就路径|认知对比|价值重塑|共同特质) \(.*?\)\n(.*?)(?=\n##|---|$)', content, re.DOTALL)
            if match: mermaid = match.group(2).strip()
            if not mermaid:
                match = re.search(r'```mermaid\n(.*?)\n```', content, re.DOTALL)
                if match: mermaid = f"```mermaid\n{match.group(1).strip()}\n```"

        # Final Formatting
        new_content = f"""---
{frontmatter.strip()}
---

# {base}

## 视频描述 (Video Description)
{desc if desc else "（无描述）"}

## 语音转录 (Transcript)
{transcript if transcript else "（无转录）"}

---
Analysis Section:

## 核心摘要 (Core Summary)
{summary if summary else "（待补充摘要）"}

## 深度见解 (Deep Insights)
{insights if insights else "（待补充见解）"}

## 逻辑映射 (Mermaid Diagrams)
{mermaid if mermaid else "（无图表）"}

---
> [!NOTE]
> 笔记由 Antigravity 自动重构，整合了原始内容与深度分析。
"""
        
        # Write to target
        with open(target_file, 'w') as f:
            f.write(new_content)
        
        # Cleanup other files if they are different from target
        for f in files:
            file_path = os.path.join(TARGET_DIR, f)
            if os.path.abspath(file_path) != os.path.abspath(target_file):
                print(f"Deleting redundant file: {f}")
                os.remove(file_path)

if __name__ == "__main__":
    merge_files()
