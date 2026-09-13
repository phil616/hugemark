//! Parse once, resolve references globally, and split only at AST boundaries.
use anyhow::{Result, bail};
use comrak::{
    Arena, Options,
    nodes::{Ast, AstNode, Node, NodeValue},
};
use serde::{Deserialize, Serialize};
use std::cell::RefCell;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Heading {
    pub id: String,
    pub title: String,
    pub level: u8,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Block {
    pub html: String,
    pub markdown: String,
    pub heading: bool,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Document {
    pub blocks: Vec<Block>,
    pub headings: Vec<Heading>,
}

pub fn options() -> Options<'static> {
    let mut o = Options::default();
    o.extension.table = true;
    o.extension.strikethrough = true;
    o.extension.autolink = true;
    o.extension.tasklist = true;
    o.extension.footnotes = true;
    o.extension.alerts = true;
    o.extension.math_dollars = true;
    o.extension.math_code = true;
    o.render.r#unsafe = true;
    o
}
fn render(node: Node<'_>, options: &Options<'_>) -> Result<String> {
    let mut html = String::new();
    comrak::format_html(node, options, &mut html)?;
    Ok(html)
}
fn alloc<'a>(arena: &'a Arena<'a>, original: Node<'a>, value: NodeValue) -> Node<'a> {
    arena.alloc(AstNode::new(RefCell::new(Ast::new_with_sourcepos(
        value,
        original.data.borrow().sourcepos,
    ))))
}
fn copy_tree<'a>(arena: &'a Arena<'a>, node: Node<'a>) -> Node<'a> {
    let out = alloc(arena, node, node.data.borrow().value.clone());
    for child in node.children() {
        out.append(copy_tree(arena, child));
    }
    out
}
fn midpoint(s: &str) -> Option<usize> {
    if s.chars().count() < 2 {
        return None;
    }
    let mut p = s.len() / 2;
    while !s.is_char_boundary(p) {
        p += 1;
    }
    // Prefer a line boundary without leaving a disproportionately large half.
    if let Some(n) = s[p..].find('\n')
        && p + n + 1 < s.len() * 3 / 4
    {
        p += n + 1;
    }
    (p > 0 && p < s.len()).then_some(p)
}
/// Split a subtree in two, retaining its container and inline formatting.
fn bisect<'a>(arena: &'a Arena<'a>, node: Node<'a>) -> Result<(Node<'a>, Node<'a>)> {
    let value = node.data.borrow().value.clone();
    let children: Vec<_> = node.children().collect();
    let left = alloc(arena, node, value.clone());
    let right = alloc(arena, node, value.clone());
    let set_text = |s: &str, make: &dyn Fn(String) -> NodeValue| -> Result<()> {
        let p = midpoint(s).ok_or_else(|| {
            anyhow::anyhow!(
                "indivisible oversized block at {:?}",
                node.data.borrow().sourcepos
            )
        })?;
        left.data.borrow_mut().value = make(s[..p].to_owned());
        right.data.borrow_mut().value = make(s[p..].to_owned());
        Ok(())
    };
    match &value {
        NodeValue::Math(_) => {
            bail!("formula exceeds the chunk budget; simplify it or increase --chunk-bytes")
        }
        NodeValue::CodeBlock(code)
            if matches!(
                code.info.split_whitespace().next(),
                Some("mermaid" | "math" | "latex" | "tex")
            ) =>
        {
            bail!("diagram/formula exceeds the chunk budget; simplify it or increase --chunk-bytes")
        }
        NodeValue::CodeBlock(code) => set_text(&code.literal, &|s| {
            let mut c = code.clone();
            c.literal = s;
            NodeValue::CodeBlock(c)
        })?,
        NodeValue::Text(text) => set_text(text, &|s| NodeValue::Text(s.into()))?,
        NodeValue::Code(code) => set_text(&code.literal, &|s| {
            let mut c = code.clone();
            c.literal = s;
            NodeValue::Code(c)
        })?,
        // Raw HTML is opaque to the Markdown AST. Never cut through its tags.
        NodeValue::HtmlBlock(_) | NodeValue::HtmlInline(_) | NodeValue::Raw(_) => bail!(
            "oversized raw HTML at {:?}; divide it into smaller complete HTML blocks",
            node.data.borrow().sourcepos
        ),
        NodeValue::Table(_) if children.len() > 2 => {
            let middle = 1 + (children.len() - 1) / 2;
            left.append(copy_tree(arena, children[0]));
            right.append(copy_tree(arena, children[0]));
            for (i, child) in children.iter().enumerate().skip(1) {
                if i < middle {
                    left.append(child);
                } else {
                    right.append(child);
                }
            }
        }
        _ if children.len() > 1 => {
            if matches!(value, NodeValue::Table(_) | NodeValue::TableRow(_)) {
                bail!(
                    "a single table row exceeds the chunk budget at {:?}; reduce cell content or increase --chunk-bytes",
                    node.data.borrow().sourcepos
                );
            }
            let middle = children.len() / 2;
            if let NodeValue::List(ref mut list) = right.data.borrow_mut().value {
                list.start += middle;
            }
            for (i, child) in children.into_iter().enumerate() {
                if i < middle {
                    left.append(child);
                } else {
                    right.append(child);
                }
            }
        }
        _ if children.len() == 1 => {
            let (a, b) = bisect(arena, children[0])?;
            left.append(a);
            right.append(b);
        }
        _ => bail!(
            "indivisible oversized node at {:?}",
            node.data.borrow().sourcepos
        ),
    }
    Ok((left, right))
}
fn bounded<'a>(
    arena: &'a Arena<'a>,
    node: Node<'a>,
    limit: usize,
    options: &Options<'_>,
    out: &mut Vec<Block>,
    depth: u8,
) -> Result<()> {
    let html = render(node, options)?;
    // Bound markup, node count, and image count rather than source bytes alone.
    let nodes = node.descendants().count();
    let images = node
        .descendants()
        .filter(|n| matches!(n.data.borrow().value, NodeValue::Image(_)))
        .count();
    if html.len() <= limit && nodes <= 4000 && images <= 16 {
        let mut markdown = String::new();
        comrak::format_commonmark(node, options, &mut markdown)?;
        out.push(Block {
            html,
            markdown,
            heading: matches!(node.data.borrow().value, NodeValue::Heading(h) if h.level<=3),
        });
    } else {
        if depth >= 32 {
            bail!("oversized block exceeds maximum planning depth");
        }
        let (a, b) = bisect(arena, node)?;
        bounded(arena, a, limit, options, out, depth + 1)?;
        bounded(arena, b, limit, options, out, depth + 1)?;
    }
    Ok(())
}

pub fn parse(source: &str, limit: usize) -> Result<Document> {
    let arena = Arena::new();
    let options = options();
    let root = comrak::parse_document(&arena, source, &options);
    let mut headings = Vec::new();
    let mut slugs = comrak::Anchorizer::new();
    let nodes: Vec<_> = root.descendants().collect();
    let footnotes: std::collections::HashMap<String, u32> = nodes
        .iter()
        .filter_map(|node| {
            if let NodeValue::FootnoteReference(reference) = &node.data.borrow().value {
                Some((reference.name.clone(), reference.ix))
            } else {
                None
            }
        })
        .collect();
    for node in nodes {
        let value = node.data.borrow().value.clone();
        match value {
            NodeValue::Heading(h) => {
                let title: String = node
                    .descendants()
                    .filter_map(|n| match &n.data.borrow().value {
                        NodeValue::Text(s) => Some(s.to_string()),
                        NodeValue::Code(c) => Some(c.literal.clone()),
                        NodeValue::SoftBreak | NodeValue::LineBreak => Some(" ".into()),
                        _ => None,
                    })
                    .collect();
                let id = slugs.anchorize(&title);
                // An invisible link annotation supplies the exact destination after pagination.
                let marker = format!(
                    "<a class=\"hm-anchor\" id=\"{}\" href=\"https://hugemark.invalid/dest/{}\">&#8203;</a>",
                    escape(&id),
                    escape(&id)
                );
                node.prepend(alloc(&arena, node, NodeValue::Raw(marker)));
                headings.push(Heading {
                    id,
                    title,
                    level: h.level,
                });
            }
            NodeValue::Link(mut link) if link.url.starts_with('#') => {
                link.url = format!("https://hugemark.invalid/link/{}", &link.url[1..]);
                node.data.borrow_mut().value = NodeValue::Link(link);
            }
            _ => {}
        }
    }
    let mut blocks = Vec::new();
    let children: Vec<_> = root.children().collect();
    for child in children {
        let footnote_number =
            if let NodeValue::FootnoteDefinition(definition) = &child.data.borrow().value {
                footnotes.get(&definition.name).copied()
            } else {
                None
            };
        let start = blocks.len();
        bounded(&arena, child, limit, &options, &mut blocks, 0)?;
        if let Some(number) = footnote_number {
            for block in &mut blocks[start..] {
                block.html = block
                    .html
                    .replacen("<ol>", &format!("<ol start=\"{number}\">"), 1)
                    .replace(
                        "data-footnote-backref-idx=\"1",
                        &format!("data-footnote-backref-idx=\"{number}"),
                    )
                    .replace(
                        "Back to reference 1",
                        &format!("Back to reference {number}"),
                    );
            }
        }
    }
    Ok(Document { blocks, headings })
}
pub fn escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub fn plan(blocks: Vec<Block>, limit: usize) -> Vec<Vec<Block>> {
    let mut chunks = Vec::new();
    let mut current = Vec::new();
    let mut size = 0;
    for block in blocks {
        if !current.is_empty()
            && (size + block.html.len() > limit
                || current.len() >= 250
                || (block.heading && size > limit / 2))
        {
            chunks.push(std::mem::take(&mut current));
            size = 0;
        }
        size += block.html.len();
        current.push(block);
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn references_resolved_across_blocks() {
        let d = parse("[later][r]\n\n# Later\n\n[r]: https://example.com\n", 4096).unwrap();
        assert!(d.blocks[0].html.contains("https://example.com"));
    }
    #[test]
    fn giant_cjk_code_and_paragraph_preserve_text() {
        for source in [
            format!("```text\n{}\n```", "中文abc\n".repeat(2000)),
            "中文abc".repeat(2000),
        ] {
            let d = parse(&source, 1024).unwrap();
            assert!(d.blocks.len() > 5);
            assert!(d.blocks.iter().all(|b| b.html.len() <= 1024));
            assert_eq!(
                d.blocks
                    .iter()
                    .map(|b| b.html.matches("中文").count())
                    .sum::<usize>(),
                2000
            );
        }
    }
    #[test]
    fn table_headers_repeat_and_rows_survive() {
        let source = format!(
            "| Key | Value |\n|---|---|\n{}",
            (0..500)
                .map(|i| format!("| ROW{i} | 中文 |\n"))
                .collect::<String>()
        );
        let d = parse(&source, 2048).unwrap();
        assert!(d.blocks.len() > 1);
        for b in &d.blocks {
            assert!(b.html.contains("<th>Key</th>"));
        }
        let all = d.blocks.iter().map(|b| b.html.as_str()).collect::<String>();
        for i in 0..500 {
            assert_eq!(all.matches(&format!(">ROW{i}<")).count(), 1);
        }
    }
    #[test]
    fn gfm_and_global_slugs() {
        let d = parse(
            "# 中文\n\n# 中文\n\n- [x] done\n\n> [!NOTE]\n> hi\n\n~~gone~~",
            4096,
        )
        .unwrap();
        assert_eq!(d.headings[1].id, "中文-1");
        let html = d.blocks.iter().map(|b| b.html.as_str()).collect::<String>();
        assert!(html.contains("checkbox"));
        assert!(html.contains("markdown-alert"));
        assert!(html.contains("<del>"));
    }
    #[test]
    fn unique_slug_collisions() {
        let d = parse("# A\n\n# A\n\n# A-1\n\n# A", 4096).unwrap();
        assert_eq!(
            d.headings.iter().map(|h| h.id.as_str()).collect::<Vec<_>>(),
            vec!["a", "a-1", "a-1-1", "a-2"]
        );
    }

    #[test]
    fn math_and_diagrams_remain_atomic() {
        let document = parse("Inline $x^2$\n\n$$x+1$$", 4096).unwrap();
        assert!(
            document
                .blocks
                .iter()
                .any(|b| b.html.contains("data-math-style"))
        );
        for language in ["mermaid", "math", "latex", "tex"] {
            let source = format!("```{language}\n{}\n```", "x".repeat(8192));
            assert!(parse(&source, 2048).is_err());
        }
    }

    #[test]
    #[ignore = "large acceptance fixture; run explicitly"]
    fn oversized_acceptance() {
        let code = "print('中文')\n".repeat(350_000);
        assert!(code.len() > 5_000_000);
        let d = parse(&format!("```python\n{code}```"), 32_768).unwrap();
        assert!(d.blocks.iter().all(|b| b.html.len() <= 32_768));
        assert_eq!(
            d.blocks
                .iter()
                .map(|b| b.html.matches("print(").count())
                .sum::<usize>(),
            350_000
        );
        let table = format!(
            "| id | 内容 |\n|---|---|\n{}",
            (0..100_000)
                .map(|i| format!("| row-{i} | 中文 |\n"))
                .collect::<String>()
        );
        let d = parse(&table, 32_768).unwrap();
        assert!(
            d.blocks
                .iter()
                .all(|b| b.html.len() <= 32_768 && b.html.contains("<th>id</th>"))
        );
        assert_eq!(
            d.blocks
                .iter()
                .map(|b| b.html.matches(">row-").count())
                .sum::<usize>(),
            100_000
        );
        let paragraph = "文".repeat(2_000_000);
        let d = parse(&paragraph, 32_768).unwrap();
        assert!(d.blocks.iter().all(|b| b.html.len() <= 32_768));
        assert_eq!(
            d.blocks
                .iter()
                .map(|b| b.html.matches('文').count())
                .sum::<usize>(),
            2_000_000
        );
    }
    #[test]
    fn footnote_definition_numbers_are_global() {
        let d = parse("One[^a], two[^b].\n\n[^a]: Alpha.\n\n[^b]: Beta.", 4096).unwrap();
        assert!(d.blocks[1].html.contains("<ol start=\"1\">"));
        assert!(d.blocks[2].html.contains("<ol start=\"2\">"));
        assert!(d.blocks[2].html.contains("Back to reference 2"));
    }
}
