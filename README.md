# OntoCore

从保险产品说明书抽取对象、属性、关系与实例，并投影到图。实现以对象关系规格为准（见 `docs/superpowers/specs/2026-09-15-ontocore-objects-relations-design.md`）。空库启动，无种子数据、无领域包。

## 后端

需要 Python 3.12。在 `backend` 目录：

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
python -m uvicorn ontocore.api.app:create_app --factory --port 8001
python -m pytest -v
```

也可用 `uv`：`uv venv --python 3.12 .venv` 后 `uv pip install --python .venv -e ".[dev]"`，再用 `.venv` 里的 Python 跑同样的 uvicorn / pytest。

数据目录默认临时目录。环境变量：

- `NEO4J_URI`（可选；未设则用内存图）
- `NEO4J_USER` / `NEO4J_PASSWORD`
- `OPENAI_API_KEY` 或其它 LiteLLM 厂商密钥（在设置页登记供应商）

可选图库（仅 Neo4j）：

```powershell
docker compose up -d
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "testtesttest"
```

无 OCR：扫描件或加密 PDF 会提示「无法提取文本」。

## 前端

```powershell
cd frontend
npm install
npm test
npm run dev
```

浏览器打开 Vite 地址（默认代理 `/api` 到 `http://127.0.0.1:8001`）。

## 开发

约定见 [`docs/dev-standards.md`](docs/dev-standards.md)：新改动必须有测试覆盖；产品文案只用对象、属性、关系、定义、实例、父对象；前端视觉参考 Dify 浅色工作台。Git 见 [`docs/git-workflow.md`](docs/git-workflow.md)。

## 演示路径

1. 在设置添加供应商、拉取模型并保存。
2. 上传 `backend/tests/fixtures/sample.txt` 或真实产品说明书；选择供应商、具体模型，可选嵌入模型和「选择引导」。
3. 在「审阅」接受对象等类型候选（有相似时选覆盖、新增或融合）后点「投影到图」。
4. 类型网与实例网按编号查询；改显示名后图上标签同步。
