# LocalFace Studio

LocalFace Studio 是一个以隐私优先为原则、完全本地运行的单张照片精准换脸 Web 应用。

当前状态：阶段 7 隐私、水印与安全验收已完成；默认启动路径可在本机通过 GPU 执行真实单人换脸，并保留显式 CPU 降级。阶段 8 正在实现默认关闭的可选 ComfyUI 适配器。

公开仓库：[Wenqi77Zhang/localface-studio](https://github.com/Wenqi77Zhang/localface-studio)

## Windows 快速开始

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1
```

初始化不需要管理员权限。受许可证限制的人脸模型不会进入 Git 仓库或安装包，需要按[本地开发指南](docs/DEVELOPMENT.md)单独取得并核验。启动后仅监听本机回环地址。

## 已冻结的产品方向

- 第一版处理单张照片，并为视频扩展预留接口。
- 默认使用本地原生 Python/ONNX 推理后端，不依赖 ComfyUI 才能运行。
- Web 应用内置节点式流程可视化；ComfyUI 作为未来可选扩展后端。
- 目标图支持多脸检测，但每次只选择并替换一个目标人物。
- 第一版严格零付费，默认只监听本机地址。
- 研究模型仅用于个人学习与非商业演示；产品代码和后端接口保持可替换。
- 导出文件写入 AI 编辑元数据；可见水印默认开启，但允许用户关闭。
- 模型、人脸图片、身份向量、缓存与生成结果不得提交到 GitHub。

## 阶段 0 文档

- [产品需求](docs/PRODUCT_REQUIREMENTS.md)
- [项目路线图](docs/PROJECT_PLAN.md)
- [架构决策](docs/architecture/ADR-001-hybrid-backend.md)
- [工具链与目录结构决策](docs/architecture/ADR-002-toolchain-and-layout.md)
- [本地开发指南](docs/DEVELOPMENT.md)
- [许可证清单](docs/LICENSE_INVENTORY.md)
- [隐私与威胁模型](docs/PRIVACY_THREAT_MODEL.md)
- [第一版验收标准](docs/ACCEPTANCE_CRITERIA.md)
- [阶段 0 进展日志](docs/progress/phase-00.md)
- [阶段 1 进展日志](docs/progress/phase-01.md)
- [阶段 2 进展日志](docs/progress/phase-02.md)
- [阶段 3 进展日志](docs/progress/phase-03.md)
- [阶段 4 进展日志](docs/progress/phase-04.md)
- [阶段 5 进展日志](docs/progress/phase-05.md)
- [阶段 6 进展日志](docs/progress/phase-06.md)
- [阶段 7 进展日志](docs/progress/phase-07.md)
- [真实换脸质量基线](docs/benchmarking/FACE_SWAP_QUALITY_BASELINE.md)
- [阶段 7 安全验收](docs/security/PHASE_07_SECURITY_ACCEPTANCE.md)
- [旧项目脱敏复盘](docs/research/LEGACY_PROJECT_REVIEW.md)

## 当前阶段

阶段 0–2 已形成完整的本地产品与模拟回归闭环；阶段 3 已实现 YuNet 默认检测、SCRFD 非商业研究选项、多脸稳定编号与单人选择，并完成同一冻结集的本地对比。阶段 4 已接入受双重许可证门禁保护的 ArcFace 与 InSwapper 真实后端，完成选中人物恢复、CUDA 实际推理验证、显式 CPU 降级、结果检查和完整 API 演练。阶段 5 新增可审计的身份优先与平衡质量预设。阶段 6 完成 7 组真实样例、14 次换脸的身份、几何、背景保护、色彩和性能基线，并如实记录自动指标无法识别的明显伪影。所有研究权重、测试人物图片、评测明细与生成结果始终由 Git 隔离。
