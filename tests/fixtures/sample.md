# Hugemark 大文档排版

中文、English、日本語、한국어。支持 **粗体**、*斜体*、~~删除~~ 和 `inline code`。

[跳到第二章](#第二章) · [外部链接](https://example.com)

> [!NOTE]
> 分块渲染，每个 Worker 只处理有界 HTML。

- [x] Markdown AST 分块
- [ ] 检查字体和跨页表格

1. 第一项
2. 第二项

| 类型 | 示例 | 状态 |
|---|---|---|
| 中文 | 字体嵌入 | 完成 |
| English | Renderer | Complete |

```python
def greet(name):
    # 中英文代码注释
    return f"Hello, {name}!"
```

![示例图片](sample.svg)

这是一个脚注引用[^note]。

[^note]: 脚注内容，应该可见。

# 第二章

第二章的正文。[回到开始](#hugemark-大文档排版)

<div style="border:1px solid #ddd;padding:12px">Raw HTML 内容</div>
