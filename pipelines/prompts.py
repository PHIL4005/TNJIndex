"""Vision prompts (Phase 02). Keep in sync with docs/architecture/tech_design.md §3."""

# Final prompt for one-shot JSON annotation (M1).
VISION_ANNOTATION_PROMPT = """你是一个《猫和老鼠》梗图标注专家。分析这张图片，用 JSON 返回以下字段：

{
  "title": "snake_case 短标题，描述画面核心内容，同时适合作为文件名，仅含小写英文/数字/下划线，≤ 80 字符",
  "tags": ["3～8 个简短标签，覆盖：角色、情绪/氛围、画面动作、可用于的社区语境"],
  "description": "1～3 句话，描述画面内容与氛围，以及这张图「迷之契合」什么类型的讨论语境，≤ 500 字符"
}

只返回 JSON，不要其他内容。"""
