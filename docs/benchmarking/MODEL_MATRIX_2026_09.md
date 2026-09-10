# 2026-09 双模型真实对比与资源稳定性

采集日期：2026-09-10 UTC；整理日期：2026-09-11。本机 Windows、Python 3.14、ONNX Runtime GPU 1.26.0；全部推理在本地完成，没有付费 API。

## 选型与方法

AlphaFace 为 2026 年研究模型，依据[作者仓库](https://github.com/andrewyu90/Alphaface_Official)、[论文](https://arxiv.org/abs/2601.16429)及于 2026-09-03 加入该模型的 [FaceFusion 3.9.0](https://github.com/facefusion/facefusion/releases/tag/3.9.0)。本项目采用其固定 ONNX 输入约定，自行实现适配，不引入 FaceFusion 运行时。

作者代码 MIT 与转换权重分发限制不是同一件事；当前转换模型加上 ArcFace 依赖仍按非商业研究处理。摘要、大小和来源见 `config/models.json`。

- 7 组既有授权样例，同一来源身份、7 个目标；不是独立身份大样本，不评估公平性。
- 两模型使用相同 SCRFD、目标选择与 ArcFace 来源编码，均输出基础与局部色彩优化两个 PNG 版本。
- 输出重新检测并与目标几何匹配后，计算 ArcFace 身份嵌入余弦相似度；不是完整画面 LPIPS，也不替代人工观察。
- 同一进程先运行 InSwapper，再运行 AlphaFace；后者共享已预热 CUDA 环境，不能公平横比首任务冷启动时间。
- RSS 包括模型、评测器和分配器保留内存；显存为整设备 nvidia-smi 采样，包括其他进程，不是单进程精确 CUDA 分配峰值。
- 人物图、逐例结果、明细与身份向量不公开；只发布汇总数据。

## 结果

| 指标 | InSwapper 128 | AlphaFace 256 |
| --- | ---: | ---: |
| 真实任务成功 | 7/7 | 7/7 |
| 基础版身份余弦中位数 | 0.81652 | 0.75299 |
| 优化版身份余弦中位数 | 0.81793 | 0.75202 |
| 第 2–7 次双结果任务耗时中位数 | 4.559 秒 | 4.168 秒 |
| 首任务耗时（不可作冷启动横比） | 60.273 秒 | 5.637 秒 |
| 进程 RSS 采样峰值 | 1898.36 MB | 978.66 MB |
| 整设备显存采样峰值 | 5310 MB | 6338 MB |

优化版相对基础版最差身份余弦变化分别约 -0.00347 和 -0.00424。不能宣称每张图片增强后身份分数都提升；保留双版本让用户直接选择。

查看人脸裁剪联系表后，AlphaFace 在部分侧脸、纹理与融合上更平顺，但部分场景身份更弱；复杂眼妆样例仍可见双眼轮廓/重影。此检查不是盲评。7/7 执行成功不等于 7/7 审美通过，困难质量门没有全部解决。因此仍默认 InSwapper，AlphaFace 供逐图比较。

## 连续运行

切回 InSwapper，同一后端、不重启进程连续处理同一组图 20 次，任务结束 RSS（MB）：

```text
493.16, 527.84, 528.52, 528.55, 529.15,
529.17, 529.76, 529.83, 530.40, 530.41,
530.98, 530.98, 531.62, 531.65, 532.16,
532.19, 532.20, 532.21, 532.21, 532.21
```

后段趋于平台，没有在此次有限测试中继续线性增长；这不能证明没有泄漏或替代多小时高负载。仍需更多输入尺寸/身份、其他 GPU 与干净 Windows 设备测试。

## 复现

安装模型并准备私有 `schema_version: 1` cases 清单后，确认影像授权与非商业研究用途，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_model_matrix --cases runtime/benchmarks/real/swap-quality-cases.json --output runtime/benchmarks/model-matrix-new --repeats 20 --confirm-image-authorization --accept-research-license
```

输出必须是 `runtime` 下的新目录，防止覆盖证据。脚本不联网下载模型。结构测试采用注入引擎，不冒充真实质量证据；本报告数值来自另行执行的真实模型。
