# OntoCore Sigma 图渲染（A 档）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 graphology + ForceAtlas2 + sigma 替换 `TypeNetwork` 的 SVG 圆环图，定义页与实例图页共用，保留点选并加上缩放/拖拽/复位，视觉保持浅色 Dify 工作台。

**Architecture:** 抽出纯函数 `buildNetworkGraph` 把 `{iri,label}` 节点与边建成 graphology 图；`TypeNetwork` 在有节点时挂 Sigma、跑 FA2、绑定点击与相机工具条；`InstanceNetwork` 仍只改空态文案。后端 API 不动。

**Tech Stack:** React 19、Vite 6、vitest、sigma ^3、graphology ^0.26、graphology-layout、graphology-layout-forceatlas2。

## Global Constraints

- 产品文案只用：对象、属性、关系、定义、实例、父对象（禁止类 / TBox / ABox 等）。
- 前端视觉：Dify 浅色工作台；主色约 `#155eef`；不要暗色画布。
- 新行为必须先有会失败再转绿的测试；界面改动须打开页面走主路径。
- 本档不做：时态、派生边、预算档、类型色、悬停邻居高亮、布局模式切换、世界网格、四层壳。
- 规格：`docs/superpowers/specs/2026-09-15-ontocore-sigma-graph-design.md`。
- Git：用户未要求时不要 commit；若执行步骤含 commit 且本机无 `user.name`/`user.email`，跳过 commit 并说明，勿改 git config。

---

## File map

| 文件 | 职责 |
| --- | --- |
| `frontend/src/components/buildNetworkGraph.ts` | 纯函数：nodes/edges → Graphology（可单测） |
| `frontend/src/components/buildNetworkGraph.test.ts` | 构图断言 |
| `frontend/src/components/TypeNetwork.tsx` | Sigma 画布 + FA2 + 工具条 + 点选 |
| `frontend/src/components/InstanceNetwork.tsx` | 薄封装，空态「还没有实例」 |
| `frontend/src/index.css` | `.network-canvas` / 工具条；去掉 `svg.network` |
| `frontend/package.json` | 增加 sigma / graphology 依赖 |
| `frontend/src/api.test.ts` | 接线：依赖声明 + 组件仍导出/使用 |

---

### Task 1: 依赖 + 构图纯函数（TDD）

**Files:**
- Create: `frontend/src/components/buildNetworkGraph.ts`
- Create: `frontend/src/components/buildNetworkGraph.test.ts`
- Modify: `frontend/package.json`（及 lock：`package-lock.json`）

**Interfaces:**
- Consumes: 无
- Produces:
  - `export type NetworkNode = { iri: string; label: string }`
  - `export type NetworkEdge = { iri: string; label: string; source_iri: string; target_iri: string }`
  - `export function buildNetworkGraph(nodes: NetworkNode[], edges: NetworkEdge[]): Graph`（graphology 默认 Graph）
  - 节点属性至少：`label: string`，以及初始 `x`/`y` 可在布局阶段再写；构图函数可不写坐标
  - 边用 `addEdgeWithKey(edge.iri, source, target, { label })`；若 source/target 不在图中则跳过

- [ ] **Step 1: 安装依赖**

在 `frontend` 目录：

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npm install sigma@^3.0.3 graphology@^0.26.0 graphology-layout@^0.6.1 graphology-layout-forceatlas2@^0.10.1
```

确认 `package.json` 的 `dependencies` 含：`sigma`、`graphology`、`graphology-layout`、`graphology-layout-forceatlas2`。

- [ ] **Step 2: 写失败测试**

创建 `frontend/src/components/buildNetworkGraph.test.ts`：

```ts
import { describe, it, expect } from "vitest";
import { buildNetworkGraph } from "./buildNetworkGraph";

describe("buildNetworkGraph", () => {
  it("adds nodes with labels", () => {
    const g = buildNetworkGraph(
      [
        { iri: "n1", label: "设备" },
        { iri: "n2", label: "人员" },
      ],
      [],
    );
    expect(g.order).toBe(2);
    expect(g.getNodeAttribute("n1", "label")).toBe("设备");
    expect(g.getNodeAttribute("n2", "label")).toBe("人员");
  });

  it("adds edges by iri and skips dangling endpoints", () => {
    const g = buildNetworkGraph(
      [
        { iri: "n1", label: "A" },
        { iri: "n2", label: "B" },
      ],
      [
        {
          iri: "e1",
          label: "属于",
          source_iri: "n1",
          target_iri: "n2",
        },
        {
          iri: "e-bad",
          label: "悬空",
          source_iri: "n1",
          target_iri: "missing",
        },
      ],
    );
    expect(g.size).toBe(1);
    expect(g.hasEdge("e1")).toBe(true);
    expect(g.getEdgeAttribute("e1", "label")).toBe("属于");
    expect(g.hasEdge("e-bad")).toBe(false);
  });
});
```

- [ ] **Step 3: 跑测试，确认失败**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npm test -- src/components/buildNetworkGraph.test.ts
```

Expected: FAIL（模块不存在或 `buildNetworkGraph` 未定义）。

- [ ] **Step 4: 最小实现**

创建 `frontend/src/components/buildNetworkGraph.ts`：

```ts
import Graph from "graphology";

export type NetworkNode = { iri: string; label: string };

export type NetworkEdge = {
  iri: string;
  label: string;
  source_iri: string;
  target_iri: string;
};

export function buildNetworkGraph(
  nodes: NetworkNode[],
  edges: NetworkEdge[],
): Graph {
  const g = new Graph({ multi: true, type: "directed" });
  for (const n of nodes) {
    if (!g.hasNode(n.iri)) {
      g.addNode(n.iri, { label: n.label });
    }
  }
  for (const e of edges) {
    if (!g.hasNode(e.source_iri) || !g.hasNode(e.target_iri)) continue;
    if (g.hasEdge(e.iri)) continue;
    g.addEdgeWithKey(e.iri, e.source_iri, e.target_iri, { label: e.label });
  }
  return g;
}
```

- [ ] **Step 5: 跑测试，确认通过**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npm test -- src/components/buildNetworkGraph.test.ts
```

Expected: PASS。

- [ ] **Step 6: Commit（若用户已要求提交且本机有 git 身份）**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/components/buildNetworkGraph.ts frontend/src/components/buildNetworkGraph.test.ts
git commit -m "feat: add graphology network builder for Sigma canvas"
```

若 `user.name`/`user.email` 未配置：跳过 commit，保留工作区改动。

---

### Task 2: 重写 TypeNetwork（Sigma + FA2 + 工具条）

**Files:**
- Modify: `frontend/src/components/TypeNetwork.tsx`（整文件替换）
- Modify: `frontend/src/components/InstanceNetwork.tsx`（改为从 `buildNetworkGraph` 或 `TypeNetwork` 再导出类型，避免重复定义）
- Modify: `frontend/src/index.css`（`.panel-canvas .network` → `.network-canvas`；删除 `svg.network*`）

**Interfaces:**
- Consumes: `buildNetworkGraph`、`NetworkNode`、`NetworkEdge` from `./buildNetworkGraph`
- Produces: 仍导出 `TypeNetwork`、`NetworkNode`、`NetworkEdge`、`NetworkSelect`（页面与 `InstanceNetwork` 依赖这些导出名）
  - `export type NetworkSelect = (kind: "node" | "edge", iri: string) => void`
  - props 与规格 §3.1 一致

- [ ] **Step 1: 写接线失败测试（依赖 + 组件仍导出）**

在 `frontend/src/api.test.ts` 增加（或扩展现有 describe）：

```ts
  it("TypeNetwork stack uses sigma and graphology", () => {
    const pkg = readFileSync("package.json", "utf8");
    expect(pkg.includes('"sigma"')).toBe(true);
    expect(pkg.includes('"graphology"')).toBe(true);
    expect(pkg.includes("graphology-layout-forceatlas2")).toBe(true);
    const tn = readFileSync("src/components/TypeNetwork.tsx", "utf8");
    expect(tn.includes('from "sigma"') || tn.includes("from 'sigma'")).toBe(true);
    expect(tn.includes("buildNetworkGraph")).toBe(true);
    expect(tn.includes("forceAtlas2")).toBe(true);
    expect(tn.includes("animatedZoom") || tn.includes("ZoomIn") || tn.includes("放大")).toBe(true);
  });
```

- [ ] **Step 2: 跑该测试确认当前失败或仍指向旧 SVG**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npm test -- src/api.test.ts
```

Expected: 在重写前，关于 `from "sigma"` / `forceAtlas2` 的断言 FAIL。

- [ ] **Step 3: 替换 `TypeNetwork.tsx`**

整文件改为（实现时可微调样式 class，但行为须覆盖）：

```tsx
import { useEffect, useRef, useState } from "react";
import { circular } from "graphology-layout";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { EdgeArrowProgram } from "sigma/rendering";
import {
  buildNetworkGraph,
  type NetworkEdge,
  type NetworkNode,
} from "./buildNetworkGraph";

export type { NetworkEdge, NetworkNode };
export type NetworkSelect = (kind: "node" | "edge", iri: string) => void;

const NODE_COLOR = "#155eef";
const EDGE_COLOR = "#84adff";
const LABEL_COLOR = "#101828";

export function TypeNetwork({
  nodes,
  edges,
  onSelect,
  emptyText = "还没有对象，请先新建",
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  onSelect: NetworkSelect;
  emptyText?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [layoutBusy, setLayoutBusy] = useState(false);

  useEffect(() => {
    const el = hostRef.current;
    if (!el || nodes.length === 0) {
      sigmaRef.current?.kill();
      sigmaRef.current = null;
      return;
    }

    const g = buildNetworkGraph(nodes, edges);
    g.forEachNode((id) => {
      g.mergeNodeAttributes(id, {
        size: 8,
        color: NODE_COLOR,
      });
    });
    g.forEachEdge((id) => {
      g.mergeEdgeAttributes(id, {
        size: 1.5,
        color: EDGE_COLOR,
        type: "arrow",
      });
    });

    setLayoutBusy(true);
    if (g.order > 0) {
      circular.assign(g, { scale: 120 });
      forceAtlas2.assign(g, {
        iterations: 80,
        settings: {
          ...forceAtlas2.inferSettings(g),
          gravity: 0.35,
          scalingRatio: 22,
          outboundAttractionDistribution: true,
        },
      });
    }
    setLayoutBusy(false);

    sigmaRef.current?.kill();
    const sigma = new Sigma(g, el, {
      allowInvalidContainer: true,
      renderEdgeLabels: true,
      defaultEdgeType: "arrow",
      edgeProgramClasses: { arrow: EdgeArrowProgram },
      labelColor: { color: LABEL_COLOR },
      labelSize: 13,
      labelFont: '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
      labelRenderedSizeThreshold: 4,
    });

    let dragged: string | null = null;
    sigma.on("downNode", ({ node }) => {
      dragged = node;
      if (!sigma.getCustomBBox()) sigma.setCustomBBox(sigma.getBBox());
    });
    sigma.getMouseCaptor().on("mousemovebody", (e) => {
      if (!dragged) return;
      const pos = sigma.viewportToGraph(e);
      g.setNodeAttribute(dragged, "x", pos.x);
      g.setNodeAttribute(dragged, "y", pos.y);
      e.preventSigmaDefault();
      sigma.refresh();
    });
    const endDrag = () => {
      dragged = null;
      sigma.setCustomBBox(null);
    };
    sigma.getMouseCaptor().on("mouseup", endDrag);
    sigma.getMouseCaptor().on("mouseleave", endDrag);

    sigma.on("clickNode", ({ node }) => onSelectRef.current("node", node));
    sigma.on("clickEdge", ({ edge }) => onSelectRef.current("edge", edge));

    sigmaRef.current = sigma;
    return () => {
      sigma.kill();
      if (sigmaRef.current === sigma) sigmaRef.current = null;
    };
  }, [nodes, edges]);

  if (nodes.length === 0) {
    return (
      <p className="muted" style={{ padding: "2rem", color: "var(--text)" }}>
        {emptyText}
      </p>
    );
  }

  return (
    <div className="network-shell">
      <div ref={hostRef} className="network-canvas" />
      {layoutBusy ? <div className="network-layout-hint">布局中…</div> : null}
      <div className="network-tools">
        <button
          type="button"
          className="btn-secondary"
          title="放大"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedZoom({ duration: 220 })
          }
        >
          +
        </button>
        <button
          type="button"
          className="btn-secondary"
          title="缩小"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedUnzoom({ duration: 220 })
          }
        >
          −
        </button>
        <button
          type="button"
          className="btn-secondary"
          title="复位"
          onClick={() =>
            sigmaRef.current?.getCamera().animatedReset({ duration: 300 })
          }
        >
          ⌂
        </button>
      </div>
    </div>
  );
}
```

说明：`layoutBusy` 在同步 FA2 下几乎闪一下即可；不要引入 FA2 worker（本档 YAGNI）。若 `nodes`/`edges` 数组每渲染都是新引用导致频繁重建，页面侧保持现有 `useState` 加载模式即可（仅 `load` 后更新）。

- [ ] **Step 4: 更新 `InstanceNetwork.tsx`**

```tsx
import {
  TypeNetwork,
  type NetworkEdge,
  type NetworkNode,
  type NetworkSelect,
} from "./TypeNetwork";

export type { NetworkEdge, NetworkNode, NetworkSelect };

export function InstanceNetwork({
  nodes,
  edges,
  onSelect,
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  onSelect: NetworkSelect;
}) {
  return (
    <TypeNetwork
      nodes={nodes}
      edges={edges}
      onSelect={onSelect}
      emptyText="还没有实例"
    />
  );
}
```

- [ ] **Step 5: 更新 CSS**

在 `frontend/src/index.css`：

1. 将 `.panel-canvas .network { min-height: 520px; }` 改为：

```css
.panel-canvas .network-shell,
.panel-canvas .network-canvas {
  min-height: 520px;
}
```

2. 删除 `svg.network` 整段（含 `.hit`），替换为：

```css
.network-shell {
  position: relative;
  width: 100%;
  height: 520px;
  background: #ffffff;
}
.network-canvas {
  width: 100%;
  height: 100%;
  outline: none;
}
.network-tools {
  position: absolute;
  left: 12px;
  bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 2;
}
.network-tools .btn-secondary {
  width: 36px;
  height: 36px;
  padding: 0;
  display: grid;
  place-items: center;
}
.network-layout-hint {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  font-size: 12px;
  color: var(--muted);
  background: rgb(255 255 255 / 0.9);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
}
```

若项目无 `.btn-secondary`，改用已有 `button` 样式类（与定义页次要按钮一致），或在工具条按钮上复用现有 `button` 默认样式。

- [ ] **Step 6: 跑前端测试**

```powershell
cd D:\Document\PAProject\OntoCore\frontend
npm test
```

Expected: 全部 PASS（含 `buildNetworkGraph` 与 `api.test.ts` 新断言）。

- [ ] **Step 7: Commit（条件同 Task 1）**

```powershell
git add frontend/src/components/TypeNetwork.tsx frontend/src/components/InstanceNetwork.tsx frontend/src/index.css frontend/src/api.test.ts
git commit -m "feat: render ontology and instance graphs with Sigma"
```

---

### Task 3: 手工验收（主路径）

**Files:** 无代码必改；若发现明显 bug 再回 Task 2 修并补测。

- [ ] **Step 1: 启动前后端**

按仓库 README / 现有习惯启动 API（默认图相关端口）与前端 Vite。确保 `frontend` 的 `/api` 代理指向后端。

- [ ] **Step 2: 定义页**

1. 打开「定义」：空库时应看到「还没有对象，请先新建」，控制台无 Sigma/WebGL 致命报错。
2. 新建至少 2 个对象与 1 条关系；画布出现力导向图（非完美圆环）。
3. 滚轮缩放、拖空白平移、拖节点、点「+ / − / ⌂」。
4. 点节点/边：现有对话框或检视仍打开。

- [ ] **Step 3: 图页**

1. 有投影实例时：可缩放/拖拽/复位；点选后右侧检视与删除仍可用。
2. 无实例：文案「还没有实例」。

- [ ] **Step 4: 视觉核对**

画布浅底、蓝节点、非暗色；工具条浅色小按钮。

- [ ] **Step 5: 若有修复，再跑 `npm test` 后按用户要求提交**

---

## Spec coverage (self-review)

| 规格项 | 任务 |
| --- | --- |
| 替换 TypeNetwork，Instance 薄封装 | Task 2 |
| graphology + FA2 + sigma | Task 1–2 |
| 接口不变 / onSelect | Task 2 |
| 缩放/拖拽/复位工具条 | Task 2 |
| 浅色视觉 | Task 2 CSS + 颜色常量 |
| 构图纯函数测试 | Task 1 |
| 接线测试 | Task 2 Step 1 |
| 手工主路径 | Task 3 |
| 不做时态/派生/预算等 | Global Constraints + 未列任务 |

无 TBD；类型名 `NetworkNode` / `NetworkEdge` / `NetworkSelect` / `buildNetworkGraph` 前后一致。
