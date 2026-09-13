# 公式与图表

行内公式 $E=mc^2$，以及 $\frac{a}{b}+\sqrt{x}$，与中文、English 混排。

$$
\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}
$$

```math
\begin{aligned}
f(x)&=x^2+2x+1\\
&=(x+1)^2
\end{aligned}
```

## 流程图

```mermaid
flowchart LR
  A[Markdown 文档] --> B{语义分块}
  B --> C[静态公式与图表]
  C --> D[Chromium 排版]
  D --> E[合并 PDF]
```

## 时序图

```mermaid
sequenceDiagram
  participant U as 用户
  participant C as Coordinator
  participant W as Worker
  U->>C: build
  C->>W: render chunk
  W-->>C: PDF
  C-->>U: 完整文档
```

## 状态图

```mermaid
stateDiagram-v2
  [*] --> Planned
  Planned --> Rendering
  Rendering --> Complete
  Rendering --> Retry: failure
  Retry --> Rendering
  Complete --> [*]
```
