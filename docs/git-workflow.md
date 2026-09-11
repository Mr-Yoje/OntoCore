# Git 规范（个人维护）

本仓库采用现在常见的个人项目做法：**主干开发 + 原子提交**。不为流程开分支，不走 Git Flow，不强制 PR。

## 主干

- 默认分支：`main`（GitHub / GitLab 现行默认名）。
- 日常：在 `main` 上改 → 自测 → 提交 → `git push origin main`。
- 工作区只保留正在做的那一件事，做完就提交，不要攒。

本仓库远程目前仍是 `master`。迁到 `main` 只需一次：把本地分支改名、推送 `main`、在 GitHub 把默认分支设为 `main`、再删远程 `master`。确认推送后再做这一步。

## 提交

用精简 Conventional Commits（不必写 scope、不必写 body）：

```
feat: 设置页从供应商模型列表里选择测试模型
fix: 纠正空 Base URL 时无法拉取模型
docs: 补充个人项目 Git 约定
refactor: 将设置页改为上下卡片布局
style: 按 Dify 浅色工作台调整界面
chore: 忽略本地数据与 Python 缓存
```

规则：

- 一次提交一件事；互不相关的改动拆开。
- 第一行：`类型: 说明`，说明用中文或英文均可，写清为什么/做成了什么。
- 提交前：后端跑相关 pytest，前端跑相关 vitest；改了界面就打开页面看一眼。
- 没要求「提交」或「推送」时，不要执行 `git commit` / `git push`。

## 分支

默认不开功能分支。

仅当大重构会让主干暂时不能用，或要同时试两条互斥实现时，从 `main` 拉短分支，做完立刻合回并删除。本地 merge 即可，不强制 PR。

不要对已推送的主干 `--force` / `hard reset`，除非当时明确要求。

## 什么进仓库

进：源码、测试、规格、本规范、为安装可复现而需要的锁文件。

不进：密钥、本机运行数据、虚拟环境、依赖目录、构建与缓存。本仓库对应为：

- `backend/data/`（含 oxigraph 与本机 `settings.json`）
- `.venv`、`node_modules`、`__pycache__`、`*.egg-info`、`.pytest_cache`、`.env`
