# LocalFace Studio

LocalFace Studio 是一个以隐私优先为原则、完全本地运行的单张照片精准换脸 Web 应用。

当前状态：阶段 0–13 的候选版工程工作已完成，版本为 `1.0.0rc2`；等待产品负责人集中视觉验收和独立干净 Windows 复现后，才允许创建稳定 `v1.0.0` 标签。

公开仓库：[Wenqi77Zhang/localface-studio](https://github.com/Wenqi77Zhang/localface-studio)

## Windows 快速开始

```powershell
.\setup.cmd
.\diagnose.cmd
.\start.cmd
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
- [阶段 8 进展日志](docs/progress/phase-08.md)
- [阶段 9 进展日志](docs/progress/phase-09.md)
- [阶段 10 进展日志](docs/progress/phase-10.md)
- [阶段 11 进展日志](docs/progress/phase-11.md)
- [阶段 12 进展日志](docs/progress/phase-12.md)
- [阶段 13 进展日志](docs/progress/phase-13.md)
- [v1 最终集中验收清单](docs/FINAL_ACCEPTANCE.md)
- [候选版说明](docs/releases/v1.0.0-rc1.md)
- [RC2 成熟度加固说明](docs/releases/v1.0.0-rc2.md)
- [成熟度审计](docs/MATURITY_AUDIT.md)
- [公网部署就绪门禁](docs/PUBLIC_DEPLOYMENT_READINESS.md)
- [发布、更新与回滚流程](docs/RELEASE_PROCESS.md)
- [视频扩展接口冻结](docs/VIDEO_EXTENSION_CONTRACT.md)
- [用户手册](docs/USER_GUIDE.md)
- [第三方组件声明](docs/licenses/THIRD_PARTY_NOTICES.md)
- [Windows 可复现性实测](docs/REPRODUCIBILITY_REPORT.md)
- [可选 ComfyUI 适配器](docs/COMFYUI_ADAPTER.md)
- [真实换脸质量基线](docs/benchmarking/FACE_SWAP_QUALITY_BASELINE.md)
- [阶段 7 安全验收](docs/security/PHASE_07_SECURITY_ACCEPTANCE.md)
- [旧项目脱敏复盘](docs/research/LEGACY_PROJECT_REVIEW.md)

## 当前阶段

阶段 0–13 已形成完整的本地单张照片候选产品、真实研究后端、质量基线、隐私安全验收、可选 ComfyUI 适配、Windows 交付链和公开仓库治理。RC2 增加了可跨后端重启的 24 小时本地会话、可解释处理就绪状态、Dependabot 与 CodeQL，并补齐人工放大质检与一键隐私安全诊断。阶段 6 的 7 组真实样例中有 2 组明显伪影，因此候选版不会用自动分数冒充美学合格。视频仅冻结 v2 接口，尚未实现。公网生产仍被许可证、账户隔离、滥用治理和法律审查门禁阻止；所有研究权重、测试人物图片、评测明细与生成结果始终由 Git 隔离。
