# 开发规范

个人维护的 OntoCore 日常开发约定。规格以 [`superpowers/specs/2026-09-15-ontocore-objects-relations-design.md`](superpowers/specs/2026-09-15-ontocore-objects-relations-design.md) 为准。Git 见 [`git-workflow.md`](git-workflow.md)。

## 产品语言

界面、API 说明、错误信息只用：对象、属性、关系、定义、实例、父对象。

不要出现：类、TBox、ABox、对象属性、数据属性、领域包。

空库启动：无种子对象、无领域包。

## 前端视觉（Dify）

界面视觉以 [Dify](https://dify.ai) 产品工作台为参照，不要退回旧的暗色测绘台风。

- 浅色工作台：白侧栏、灰画布、白卡片；圆角偏大。
- 主色蓝约 `#155eef`（或同系蓝）；字体用 Noto Sans SC。
- 产品文案仍只用：对象、属性、关系、定义、实例、父对象。禁止用「类」作产品文案。

改布局或样式时，核对是否仍符合上述语言，而不是另起一套皮肤。

## 错误码与异常提示

新增或改动会失败的路径时，必须接入现有故障码体系（规格见 [`superpowers/specs/2026-09-21-fault-logging-design.md`](superpowers/specs/2026-09-21-fault-logging-design.md)），不能只 `raise Exception` / 返回裸字符串。

| 约定 | 要求 |
| --- | --- |
| 异常类型 | 走 `ontocore.errors` 的 `AppError` 谱系（`BusinessError` / `SystemError` 或既有子类）；必要时在 `errors.py` 增加带默认 `code` 的子类 |
| 故障码 | 稳定码 `OC-xxxx`，按段选用：1xxx 入参/未找到、2xxx 对象属性关系写入、3xxx 作业抽取、4xxx 图基础设施、5xxx 设置、9xxx 未捕获。新场景优先复用已有码；确需新码时在同段内递增，并同步更新 `error_catalog` 与故障码规格表 |
| 用户文案 | **一个码一句固定中文**，来自 `ontocore.error_catalog`（即 HTTP `detail` / 作业 `error`）；不含 `OC-`、不含堆栈/路径/异常类名；禁止调用点自由改写与对照表不一致的文案 |
| HTTP | 由统一处理器返回 `{detail, code, kind, request_id}`；业务 `kind=business`，系统 `kind=system` |
| 前端 | tips / 作业状态只展示友好中文；按 `kind` 选样式，**不渲染** `code` |
| 测试 | 至少断言：对应 HTTP/`AppError` 的 `code`，以及 `detail` 等于对照表固定句 |

完成自检：新失败路径能在日志里用 `OC-` 定位，界面只有可读提示。

## 测试必须覆盖新改动

没有对应测试的行为改动，不算做完，也不能提交。

| 改了什么 | 至少要有 |
| --- | --- |
| 后端行为、接口、校验、错误文案 | `backend/tests/` 里一条会失败的用例（改之前红、改之后绿） |
| 修 bug | 先写复现该 bug 的测试，再改代码 |
| 前端接口封装、页文案、关键交互接线 | `frontend/src/api.test.ts` 或同目录新测试 |
| 界面布局、样式、可点击流程 | 打开页面走一遍主路径；只截一张图不算 |

例外（仍须说明原因）：纯注释、只改本规范、只改忽略规则。`style:` 若只动 CSS 且无行为变化，可用浏览器核对代替新单测，但相关文案/选择器测试若已存在必须仍通过。

不要为凑行覆盖率加空断言。测的是用户或调用方能感知的行为。

## 怎么跑

后端（在 `backend`，数据目录由 `conftest` 指到临时目录，勿用本机 `backend/data/`）：

```powershell
cd backend
$env:PYTHONPATH = "src"
python -m pytest -q
```

只跑相关文件，例如：`python -m pytest tests/test_api.py -q`。提交前至少跑本次改动碰到的测试文件；跨模块时跑全量 `pytest`。

前端：

```powershell
cd frontend
npm test
```

测试里不要打真实模型供应商、不要读本机密钥。LLM 用假模块或假响应。

## 完成标准

1. 新行为有测试，相关测试全绿。
2. 产品文案与前端视觉符合上文约定。
3. 会失败的路径已挂 `OC-xxxx` 与中文提示（见「错误码与异常提示」）。
4. 改了页面则浏览器核对过主路径。
5. 一次提交一件事，信息符合 Git 规范。
