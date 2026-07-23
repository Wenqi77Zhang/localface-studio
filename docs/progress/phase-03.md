# 阶段 3：人脸检测与目标选择

状态：进行中  
开始日期：2026-07-24

## 已确认范围

- 默认检测器为 OpenCV YuNet，最终冻结前先完成本机兼容性与困难场景验证。
- 高级设置预留人脸检测模型选择。
- 支持 `yunet-opencv`、仅限本地非商业研究的 `scrfd-insightface-research`，并为未来 `scrfd-custom` 预留接口。
- 切换检测器后，检测框、稳定编号和人物选择全部失效并重新检测。
- 官方 InsightFace SCRFD 权重不得提交、镜像或随安装包分发。
- 商业模式由后端禁止加载研究权重。

## 当前完成

- 已比较 YuNet、SCRFD、RetinaFace 和 MediaPipe/BlazeFace 的工程适用性。
- 已确认检测模型与换脸模型的职责边界。
- 已冻结可替换检测器和许可证隔离架构，见 `docs/architecture/ADR-003-face-detector-profiles.md`。

## 下一小步

1. 登记 YuNet 候选文件、官方来源、许可证、预期大小和 SHA-256。
2. 在 Python 3.14 环境验证 OpenCV 与 YuNet 加载。
3. 使用不含个人或未授权人脸的许可测试素材验证单脸、多脸、无脸、小脸、遮挡和旋转行为。
4. 验证通过后再实现统一 `FaceDetector` 契约和前端检测流程。

## 尚未执行

- 未安装 OpenCV 或 InsightFace。
- 未下载任何模型权重。
- 未修改高级设置界面。
- 未把 YuNet 正式判定为已通过验收的默认实现。
