# OntoCore 设计：Sigma 图渲染（A 档）

日期：2026-09-15  
状态：已确认，待实现计划  
范围：前端定义页与实例图页的图渲染替换  
相关：[`2026-09-15-ontocore-objects-relations-design.md`](2026-09-15-ontocore-objects-relations-design.md)

## 1. 背景与目标

当前 `TypeNetwork` 用手写 SVG + 固定圆环布局，只能点选，不能缩放/拖拽，节点一多即难看清。对照 Utopia 的 graphology + ForceAtlas2 + sigma 栈，本轮做 **A 档最小替换**：换引擎与基础交互，不引入时态、派生边、预算档位等产品能力。

成功标准：

- 定义页与图页均用同一套 Sigma 渲染。
- 可缩放、平移、拖节点、放大/缩小/复位。
- 点选节点/边仍走现有 `onSelect`，页面检视与删除逻辑不变。
- 视觉保持 Dify 浅色工作台（蓝系节点、浅底），非暗色画布。
- 有对应前端测试；改界面后手工走主路径。

明确不做：时态过滤、派生/推理边、节点预算档、类型着色、悬停邻居高亮、布局模式切换、世界网格、四层节点壳、后端 API 变更。

## 2. 方案选择

采用 **替换 `TypeNetwork`，`InstanceNetwork` 继续薄封装**（方案 1）。

不采用：新旧组件并存（多余清理）、只先改定义页（两页体验一度不一致）。

视觉选 **跟 OntoCore 现有浅色工作台**，不跟 Utopia 深色画布。

## 3. 组件与数据流

### 3.1 对外接口（不变）

```ts
TypeNetwork({
  nodes: { iri: string; label: string }[];
  edges: { iri: string; label: string; source_iri: string; target_iri: string }[];
  onSelect: (kind: "node" | "edge", iri: string) => void;
  emptyText?: string;
})
```

`InstanceNetwork` 仍只改空态文案（「还没有实例」），内部调用 `TypeNetwork`。

### 3.2 内部流水线

1. `nodes` / `edges` 变化 → 构建 `graphology` 图（边 key = `iri`；缺端点的边跳过）。
2. 有节点时：`circular` 初铺 → `forceAtlas2` 静态若干步 → 可选短跑 worker（约 1.5–2.5s）后停止。
3. `new Sigma(graph, container)` 挂到占满 `panel-canvas` 的容器（不再写死 640×480）。
4. `clickNode` / `clickEdge` → `onSelect("node"|"edge", iri)`。
5. 数据再来时：销毁旧 Sigma 后重建（逻辑简单，本档可接受）。

### 3.3 文件与依赖

| 项 | 动作 |
| --- | --- |
| `frontend/src/components/TypeNetwork.tsx` | 重写为 graphology + FA2 + sigma |
| `frontend/src/components/InstanceNetwork.tsx` | 保持薄封装 |
| `frontend/package.json` | 增加 `sigma`、`graphology`、`graphology-layout`、`graphology-layout-forceatlas2` |
| `frontend/src/index.css` | `svg.network` 改为容器 `.network-canvas`（全高） |

后端 `/api/ontology/network`、`/api/graph/network` 与 JSON 形状本轮不改。

## 4. 交互与视觉

### 4.1 交互

| 操作 | 行为 |
| --- | --- |
| 滚轮 / 触控板 | 缩放 |
| 拖空白 | 平移 |
| 拖节点 | 移动该节点（布局停止后仍可） |
| 点节点 / 边 | 现有 `onSelect` |
| 点空白 | 不强制清空选中（检视区仍由页面状态管） |
| 角上工具条 | 放大、缩小、复位相机 |

布局进行中可显示轻量「布局中…」；结束后停 worker。

### 4.2 视觉

- 画布底：白或极浅 `--bg`，无深色网格。
- 节点：`--accent`（约 `#155eef`）实心圆 + 淡光晕。
- 边：浅蓝灰（现 `#84adff` 一带）+ 箭头。
- 标签：`--text`，字号约 13；远景用 sigma 默认标签密度即可。
- 工具条：浅底、小圆角，贴合现有按钮风格。
- 空态：无节点时只显示文案，不挂 Sigma。

## 5. 测试与验收

### 5.1 自动化

1. **构图纯函数**：`nodes/edges` → 图属性正确（label、端点、跳过坏边）。
2. **接线**：`package.json` 含上述依赖；页面仍用 `TypeNetwork` / `InstanceNetwork` + `onSelect`（`api.test.ts` 或同目录新测）。
3. **WebGL 桩**：若测 Sigma 挂载，在测试入口 mock `WebGLRenderingContext` / `WebGL2RenderingContext`。

不测：FA2 最终坐标、像素级截图。

### 5.2 手工

1. 定义页：有对象/关系时出图；缩放/拖拽/复位；点选仍开现有对话框。
2. 图页：实例网同上；检视与删除仍可用。
3. 空库：两页空态文案，无控制台致命错误。
4. 视觉为浅色蓝系，非暗色。

## 6. 名词说明（本档刻意不做）

- **时态**：按边成立区间过滤「某一天仍成立」的边。
- **派生边**：公理推出的边，可开关显示。
- **预算档位**：大图只画连接度最高的 N 个节点。

以上留待后续规格，不进入本实现计划。
