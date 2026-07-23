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
- 已在 Python 3.14.6 中验证 opencv-python-headless 5.0.0.93、NumPy 2.5.1 和 `FaceDetectorYN` 可用。
- 已从 OpenCV 官方仓库取得 `face_detection_yunet_2026may.onnx`，验证大小为 229738 字节，SHA-256 为 `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0`。
- 已完成模型加载及程序生成无脸图的 CPU 推理检查，正确返回零张人脸。
- 已建立可提交的 `config/models.json`；权重文件仍位于 Git 忽略目录。

## 下一小步

1. 使用不含个人或未授权人脸的许可测试素材验证单脸、多脸、无脸、小脸、遮挡和旋转行为。
2. 验证通过后再实现统一 `FaceDetector` 契约和前端检测流程。

## 尚未执行

- 未安装 InsightFace 或下载官方 SCRFD 研究权重。
- 未修改高级设置界面。
- 未把 YuNet 正式判定为已通过验收的默认实现。
