interface ResultPreviewProps {
  error: string | null
  loading: boolean
  outputFormat: 'png' | 'jpeg'
  previewUrl: string | null
}

function ResultPreview({
  error,
  loading,
  outputFormat,
  previewUrl,
}: ResultPreviewProps) {
  return (
    <section className="result-preview" aria-labelledby="result-preview-title">
      <div className="result-preview__heading">
        <div>
          <span className="eyebrow">Simulation result</span>
          <h3 id="result-preview-title">模拟结果预览</h3>
        </div>
        {previewUrl !== null && (
          <a
            className="result-download"
            href={previewUrl}
            download={`localface-simulation.${outputFormat === 'jpeg' ? 'jpg' : 'png'}`}
          >
            下载{outputFormat === 'jpeg' ? ' JPEG' : ' PNG'}结果
          </a>
        )}
      </div>
      <div className="result-preview__frame">
        {loading && <p>正在安全读取本地结果…</p>}
        {error && <p className="submit-error">{error}</p>}
        {previewUrl !== null && (
          <img src={previewUrl} alt="带有模拟标识的处理结果" />
        )}
      </div>
      <p className="result-preview__notice">
        当前为模拟后端输出，不代表已经执行真实换脸；AI 编辑元数据始终保留。
      </p>
    </section>
  )
}

export default ResultPreview
