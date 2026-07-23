# LocalFace Studio

LocalFace Studio 是一个以隐私优先为原则、完全本地运行的单张照片精准换脸 Web 应用。

当前状态：阶段 1 - 工程骨架与独立环境。

公开仓库：[Wenqi77Zhang/localface-studio](https://github.com/Wenqi77Zhang/localface-studio)

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
- [许可证清单](docs/LICENSE_INVENTORY.md)
- [隐私与威胁模型](docs/PRIVACY_THREAT_MODEL.md)
- [第一版验收标准](docs/ACCEPTANCE_CRITERIA.md)
- [阶段 0 进展日志](docs/progress/phase-00.md)
- [阶段 1 进展日志](docs/progress/phase-01.md)
- [旧项目脱敏复盘](docs/research/LEGACY_PROJECT_REVIEW.md)

## 当前阶段

阶段 0 已于 2026-07-23 通过产品负责人验收。阶段 1 将创建独立运行环境和可测试的前后端工程骨架。项目采用单一公开 GitHub 仓库展示演进，每次推送前必须执行敏感内容扫描；大型模型的下载仍须等待模型来源、哈希和许可证提示机制确定。
