# LocalFace Studio

LocalFace Studio 是一个以隐私优先为原则、完全本地运行的单张照片精准换脸 Web 应用。

当前版本：`1.0.0rc3`。真实本地单张照片换脸，支持 InSwapper 128 与 AlphaFace 256 切换、基础/色彩优化双结果和独立下载。阶段 16 已补齐此前缺失的处理接口、双工件与资源采样；复杂照片的视觉质量、独立干净 Windows 复现及产品负责人验收仍有边界，不创建稳定 `v1.0.0` 标签。

2026-10-30 复查已修复验证脚本访问真实运行目录和启动清理失败中断问题，173 项测试与完整工程质量门通过。公开展示项目与开放注册处理照片仍需分开验收，见[成熟度审计](docs/MATURITY_AUDIT.md)及[上线门禁](docs/PUBLIC_DEPLOYMENT_READINESS.md)。

公开仓库：[Wenqi77Zhang/localface-studio](https://github.com/Wenqi77Zhang/localface-studio)

公开展示：[LocalFace Studio 项目介绍](https://localface-studio.stonyring261.chatgpt.site)。这是独立静态介绍页，不接收访客图片、不提供在线换脸，也不连接本机服务。源码见 [showcase](showcase/README.md)，发布与验收记录见[展示版 v1](docs/releases/showcase-v1.md)。

## Windows 快速开始

```powershell
.\setup.cmd
.\diagnose.cmd
.\verify-install.cmd
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
- [阶段 14 进展日志](docs/progress/phase-14.md)
- [阶段 15 全面审查日志](docs/progress/phase-15.md)
- [阶段 16 真实模型与双结果重构](docs/progress/phase-16.md)
- [2026-09 双模型实测与连续资源曲线](docs/benchmarking/MODEL_MATRIX_2026_09.md)
- [v1 最终集中验收清单](docs/FINAL_ACCEPTANCE.md)
- [候选版使用与验收演练](docs/ACCEPTANCE_WALKTHROUGH.md)
- [候选版说明](docs/releases/v1.0.0-rc1.md)
- [RC2 成熟度加固说明](docs/releases/v1.0.0-rc2.md)
- [RC3 双模型与双结果说明](docs/releases/v1.0.0-rc3.md)
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

阶段 16 接入 2026 年 AlphaFace 研究模型，并与 InSwapper 使用相同的来源编码、检测和真实样例进行比较。两者各完成 7 个任务；本地小样本的身份相似度中位数分别为 0.753 与 0.817，因此 InSwapper 仍为默认，AlphaFace 作为可选对照，不宣称新模型全面更优。

原生路径现在真实执行 `校验 → 准备 → 换脸 → 可选色彩优化 → 检查 → 导出`。基础结果不会被增强覆盖；每个版本保留 AI 元数据，图库按任务配对并可分别下载。独立 `FaceSwapper` / `FaceEnhancer` 接口允许替换模型，不需要重写上传、会话或下载逻辑。模拟后端只保留为显式开发/测试工具，不再是配置默认值。

20 次连续任务的进程内存采样在后段趋于稳定，但有限样本不能证明无泄漏或保证所有机器性能。复杂眼妆等场景仍可能重影，色彩校正不是生成式五官修复。视频只保留接口；账号、公网推理与商业服务未实现、未部署。2026-10-30 独立发布的静态介绍页不改变这些边界。受限权重、人物图片、评测明细与生成结果始终由 Git 隔离。
