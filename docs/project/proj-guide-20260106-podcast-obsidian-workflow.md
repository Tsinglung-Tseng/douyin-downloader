# Workflow: Douyin/Podcast to Obsidian Note Generation

## 1. 目标 (Objective)
将下载的视频/播客（元数据 + 转录稿）自动化或半自动化地转化为高质量的 Obsidian 永久笔记。要求笔记兼具“原始内容的完整性”与“深度见解的可读性”。

## 2. 笔记结构规范 (Note Structure)

### Header: YAML Frontmatter
```yaml
---
property: true
title: "{{标题}}"
create_time: "{{发布时间}}"
author: "{{作者/博主}}"
source: "Douyin / Podcast"
aweme_id: "{{唯一ID}}"
type: "Video/Podcast Note"
tags: ["{{主题}}", "{{人格类型}}", "{{关键词}}"]
aliases: ["{{替代标题}}", "{{核心概念}}", "{{关联意象}}"]
---
```

### Original Section: 原始内容记录
- **## 视频/内容描述 (Description)**: 直接引用博主的原始文字描述。
- **## 语音转录 (Transcript)**: 精简或完整保留转录稿内容。

### Analysis Section: 深度分析提取
- **## 核心摘要 (Core Summary)**: 用 1-2 句话概括内容的核心论点。
- **## 深度见解 (Deep Insights)**:
    - 提取人格特质、心理机制或行为模式（搭配英文术语）。
    - 对比不同人格（如 J vs P, NT vs NF）的差异。
- **## 逻辑映射 (Mermaid Diagrams)**:
    - 使用 Mermaid `graph TD` 或 `graph LR` 可视化逻辑链条或心理动力学模型。

## 3. 专题整理提示词 (Topic Aggregation Prompt)
当需要对多个 episode 进行专题汇总时，遵循以下逻辑：
- **横向对比**: 寻找不同 episode 之间的共同点与冲突点。
- **系统重构**: 建立一个更宏观的知识框架（例如：MBTI 职场生存学、恋爱心理学）。
- **知识链接**: 在每个子笔记之间建立双向链接 `[[Note Name]]`。

## 4. 视觉标准 (Visual Standards)
- **Callouts**: 使用 `> [!TIP]`, `> [!IMPORTANT]`, `> [!NOTE]` 强调关键结论。
- **Clean Naming**: 文件名应剔除标签，保持简洁且具有检索性。
