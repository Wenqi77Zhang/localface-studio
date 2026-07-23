# ADR-002：阶段 1 工具链与目录结构

- 状态：已接受
- 日期：2026-07-23
- 决策人：产品负责人、项目工程协作者

## 背景

项目需要在 Windows 目标设备上建立可复现的本地 Web 工程，同时保持零付费、项目环境隔离、隐私优先，并为后续 ONNX 推理、可选 ComfyUI 后端和视频处理预留清晰边界。

目标设备当前已有 Python 3.14.6、Git 2.52.0、CUDA Toolkit 12.8 和支持 CUDA 13.1 的 NVIDIA 驱动，但没有可作为项目依赖使用的系统 Node.js。Codex 附带的内部 `pnpm` 不属于项目运行时，不能作为可复现环境的一部分。

## 决策

### 运行时与依赖管理

- Python 基线冻结为 **CPython 3.14.6**。
- Python 虚拟环境固定为项目根目录下的 `.venv/`。
- 使用 `uv` 管理 Python 环境与依赖，并提交 `uv.lock`；安装时记录实际使用的 `uv` 版本和下载校验值。
- Node.js 使用 **24.18.0 LTS** 的 Windows 便携发行版，放置于被忽略的 `.tools/node/`，不依赖系统级安装。
- 前端使用 Node.js 自带的 npm，提交 `package-lock.json`，自动化环境使用 `npm ci`。
- 前端框架采用 React 19、TypeScript 和 Vite 8；具体解析版本以锁文件为准。
- 后端采用 FastAPI、Pydantic 和 Uvicorn；具体解析版本以 `uv.lock` 为准。

### Python 3.14 风险控制

选择 Python 3.14.6 可以复用目标设备的现有运行时，并且当前 ONNX Runtime GPU 已提供对应 Windows wheel，InsightFace 也提供不默认构建可选 C++ 扩展的通用 wheel。

Python 3.14 仍可能遇到个别后续图像或模型扩展包尚未适配的情况。因此执行以下门禁：

1. 阶段 1 只安装 Web、测试和质量工具，不安装模型或 GPU 推理依赖。
2. 阶段 4 安装模型依赖前，先在独立分支验证 Python 3.14 的完整依赖解析、导入和 GPU 推理。
3. 只有不可替代的核心依赖存在可复现的不兼容，且上游没有可接受版本时，才将项目统一回退到 Python 3.13；不得在未记录的情况下混用两个 Python 小版本。
4. 任何回退都必须新增 ADR、更新 `.python-version`、`pyproject.toml`、锁文件和 CI，并重新运行全部门禁。

### 目录结构

```text
localface-studio/
├─ src/localface_studio/
│  ├─ api/               # HTTP 接口与输入验证
│  ├─ application/       # 用例与任务编排
│  ├─ domain/            # 核心类型、状态与规则
│  ├─ infrastructure/    # 配置、文件、日志和元数据
│  └─ backends/          # 原生 ONNX 与未来 ComfyUI 适配器
├─ tests/                # 后端和跨边界测试
├─ frontend/
│  └─ src/               # React/TypeScript 前端
├─ scripts/              # Windows 初始化、启动与诊断入口
├─ docs/                 # 决策、进展和公开脱敏文档
├─ .python-version
├─ pyproject.toml
└─ uv.lock
```

该结构采用单仓库、单 Python 包和一个前端子项目。现阶段不引入多包工作区或共享代码生成包；未来通过 OpenAPI 契约生成前端类型，避免过早增加 monorepo 复杂度。

### 安全与可复现性

- `.venv/`、`.tools/`、`node_modules/`、模型权重、用户图片、运行输出和日志不进入 Git。
- 锁文件、初始化脚本、配置模板和脱敏日志规则进入 Git。
- 下载运行时或工具时必须使用官方 HTTPS 来源，并在项目记录中保存版本、URL 和 SHA-256。
- 服务默认只绑定 `127.0.0.1`，不得在未增加身份验证和安全评审前开放到局域网或公网。

## 暂不执行

- 不在本决策步骤下载 Python、Node.js、模型或权重。
- 不安装 Visual Studio C++ Build Tools；只有实际、必要依赖证明需要本地编译时再评估。
- 不升级 CUDA Toolkit 或 NVIDIA 驱动；GPU 运行时兼容性在模型阶段单独验证。

## 参考资料

- [Python 3.14.6](https://www.python.org/downloads/release/python-3146/)
- [ONNX Runtime Python 安装说明](https://onnxruntime.ai/docs/get-started/with-python.html)
- [ONNX Runtime GPU](https://pypi.org/project/onnxruntime-gpu/)
- [InsightFace](https://pypi.org/project/insightface/)
- [uv 项目结构](https://docs.astral.sh/uv/concepts/projects/layout/)
- [uv Python 版本管理](https://docs.astral.sh/uv/concepts/python-versions/)
- [Node.js 发布计划](https://nodejs.org/en/about/previous-releases)
- [Node.js 24 最新发行目录](https://nodejs.org/download/release/latest-v24.x/)
- [npm ci](https://docs.npmjs.com/cli/commands/npm-ci/)
- [Vite 入门指南](https://vite.dev/guide/)

## 后果

正面影响：本地环境边界清晰、可复现性较强、无需管理员权限，并能在不引入模型许可证风险的情况下推进 Web 工程。

代价与风险：项目需要维护 Python 与 Node.js 两套锁文件；Python 3.14 对后续 AI 长尾依赖仍有兼容性风险，因此必须执行上述回退门禁。
