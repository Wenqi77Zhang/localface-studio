# 本地真实图片检测基准工作流

状态：`real20-v1` 已冻结，本工作流继续作为替换样本和后续版本的准入规则
制定日期：2026-07-29
首次冻结日期：2026-08-21

## 用途与边界

本工作流使用少量、逐图核验许可的真实照片，验证合成图片无法覆盖的相机噪声、自然光照、复杂背景、遮挡、旋转、裁切和人脸尺度变化。它只评价人脸检测框，不进行身份识别、身份库建设、人口属性推断或人物排名。

20 张图片只是工程冒烟基准，不构成真实世界准确率、公平性结论或商业可用性证明。

当前冻结结果的脱敏公开摘要见 [本地真实图片人脸检测基准冻结摘要](REAL_IMAGE_BASELINE_SUMMARY.md)。

## 数据源

候选图片仅从 Open Images V7 的官方图片元数据开始筛选：

- [Open Images V7 facts and figures](https://storage.googleapis.com/openimages/web/factsfigures_v7.html)
- [Open Images V7 download page](https://storage.googleapis.com/openimages/web/download_v7.html)
- [Open Images rotation metadata note](https://storage.googleapis.com/openimages/web/2018-05-17-rotation-information.html)

Open Images 将图片列为 CC BY 2.0，但同时明确不对每张图片的许可状态作保证。因此，数据集标签不能替代逐图核验。若原始落地页不可访问、作者无法确认、许可未明确显示或信息互相冲突，该候选必须拒绝。

## 本地目录

运行以下命令建立工作区：

```powershell
.\.venv\Scripts\python.exe scripts\init_local_real_benchmark.py
```

工具只会在被 Git 忽略的 `runtime/benchmarks/real/` 下创建：

- `images/`：已接受的原图；
- `reports/`：检测器的逐图本地报告；
- `license-ledger.json`：逐图许可证与来源核验台账；
- `manifest.draft.json`：人工复核检测框草稿；
- `LOCAL_ONLY.txt`：本地数据警示。

重复运行不会覆盖已有台账或人工标注。

下载官方 CSV 元数据后，运行以下命令生成 40 条本地候选审查队列：

```powershell
.\.venv\Scripts\python.exe scripts\prepare_open_images_candidates.py
```

该工具不下载图片，也不批准许可证。它会排除 Open Images 标记为描绘作品或群组框的图片、缺少来源字段的记录、旋转信息未知的记录及非 CC BY 2.0 声明，并按单脸、多脸、遮挡、裁切、大小与旋转情况生成确定性的候选顺序。输出 `candidate-review-queue.json` 位于被 Git 忽略的本地工作区。

## 单张候选的准入顺序

1. 先打开 `OriginalLandingURL`，再考虑下载图片。
2. 核对作者、作者主页、作品标题、原始链接和页面上当前显示的许可证。
3. 排除未成年人、医疗或其他敏感场景，以及可能给当事人带来额外风险的内容。
4. 只有许可证与来源都通过核验后才下载原图；不从不明转载站下载。
5. 记录核验时间、下载时间、Open Images 提供的原始 MD5 和本地下载文件的 SHA-256。
6. 解码时应用 EXIF 方向，使检测像素、API 宽高和用户实际看到的方向一致。
7. Open Images 的原始框若基于未旋转像素坐标，必须随图片执行相同的坐标变换，再人工复核所有可见人脸。
8. 不保存单独的人脸裁剪，不标注姓名、性别、年龄、种族或其他敏感属性。
9. 完成 20 张后锁定清单，再用相同图片和人工框对 YuNet 及后续 SCRFD 适配器分别评测。

## 许可证台账字段

每个候选至少记录：

- 本地匿名 `case_id`；
- Open Images `ImageID` 与子集；
- `OriginalURL`、`OriginalLandingURL`；
- 作者、作者主页、标题；
- 页面显示的许可证名称与链接；
- 来源和许可证核验时间；
- 下载时间、原始 MD5、本地 SHA-256、旋转值；
- `accepted` 或 `rejected`；
- 接受说明或具体拒绝理由；
- 仅含相对文件名的 `asset_name`，不得写入 Windows 用户目录等绝对路径。

## GitHub 发布边界

以下内容禁止提交：

- 真实原图、缩略图和人脸裁剪；
- 许可证本地台账与逐图检测结果；
- 人工人脸框清单；
- 本机绝对路径或能够反推出本地目录的信息。

公开仓库将来最多增加：

- 不含逐图身份和私人路径的合计指标；
- 测试场景数量与失败类型汇总；
- 许可证审查通过数、拒绝数及拒绝原因类别；
- YuNet 与许可证可用的其他检测器之间的同条件比较结论。
