# 架构与扩展

## 渲染过程

1. `src/document.rs` 使用 Comrak AST 解析全局引用、标题和脚注，并拆分超大语义节点。
2. 规划器按预算组合块；`src/pipeline.rs` 管理清单、缓存、资源校验、重试及自适应拆分。
3. `workers/advanced.py` 在独立浏览器中调用嵌入的 MathJax/Mermaid，将源码转换成 SVG。此页面只接收组件字符串，阻断网络。
4. `workers/render.py` 完成代码高亮，再以禁用 JavaScript 的独立打印页面输出 PDF。
5. `workers/assemble.py` 使用 pikepdf 合并页面、修复跨块跳转并写入书签与元数据。

组件缓存包含实现、库、主题、样式和源码的指纹及内容校验；重复 SVG 引用会重写 ID，避免多个公式相互干扰。公式使用独立 SVG 字形，不依赖打印页面再次加载 MathJax。

## 平台隔离

Linux 使用进程组和 subreaper 回收包括独立会话在内的 Worker 后代。Windows 使用 Job Object：包装进程先等待协调器将其加入 Job，再启动真实 Worker，超时或协调器退出时关闭整个 Job。两种平台都记录进程树 RSS；该指标不是硬内存限额。

## 增加组件

Markdown 语法由 Comrak 负责；围栏图表可在 `workers/advanced.py` 中按语言扩展成静态 SVG/HTML，无需重写分块和 PDF 合并。新组件需要确定源码限制、离线依赖、缓存标识和错误处理；不可拆分的语法还需在 AST 拆分规则中声明。新增库通过 `scripts/vendor.mjs` 固定版本并嵌入。

可通过 `--renderer /path/to/program` 替换整个渲染后端。后端接收 `HTML_PATH PDF_PATH` 两个位置参数，成功退出并写入有效 PDF；高级组件预处理属于默认后端，自定义后端需自行处理。

## 边界

完整 AST 和最终 PDF 合并仍随全文规模增长。超大 Raw HTML 不切断标签，超大表格单行或不可分割图表会明确报错。分页边界可能留白，图表会按打印页面缩放；非常宽的图可能难以阅读。没有内置打印目录、可见页码或 WeasyPrint 后端。

只提供 Linux/Windows amd64 发布程序。源码中的其他平台分支不等于经过验证的发布支持。
