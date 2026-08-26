# LocalFace Studio

LocalFace Studio 是一个以隐私优先为原则、完全本地运行的单张照片精准换脸 Web 应用。

当前状态：阶段 3 人脸检测与单人选择工程实现已完成；阶段 4 原生精准换脸后端正在实施。

公开仓库：[Wenqi77Zhang/localface-studio](https://github.com/Wenqi77Zhang/localface-studio)

## Windows 快速开始

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1
```

初始化不需要管理员权限，也不会下载人脸模型。启动后仅监听本机回环地址；详细说明见[本地开发指南](docs/DEVELOPMENT.md)。

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
- [旧项目脱敏复盘](docs/research/LEGACY_PROJECT_REVIEW.md)

## 当前阶段

阶段 0–2 已形成完整的本地模拟产品闭环；阶段 3 已实现 YuNet 默认检测、SCRFD 非商业研究选项、多脸稳定编号与单人选择，并完成同一冻结集的本地对比。研究权重始终由 Git 隔离。当前正在实现阶段 4 原生精准换脸后端；在真实后端完成前，现有任务结果仍明确标记为模拟结果。
