import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from 'react'

interface ResultPreviewProps {
  error: string | null
  loading: boolean
  originalFile: File
  outputFormat: 'png' | 'jpeg'
  previewRatio: number
  previewUrl: string | null
}

const DEFAULT_COMPARISON_POSITION = 50
const KEYBOARD_STEP = 2

function ResultPreview({
  error,
  loading,
  originalFile,
  outputFormat,
  previewRatio,
  previewUrl,
}: ResultPreviewProps) {
  const [comparisonPosition, setComparisonPosition] = useState(
    DEFAULT_COMPARISON_POSITION,
  )
  const [originalUrl, setOriginalUrl] = useState<string | null>(null)
  const comparisonRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const objectUrl = URL.createObjectURL(originalFile)
    setOriginalUrl(objectUrl)
    setComparisonPosition(DEFAULT_COMPARISON_POSITION)
    return () => URL.revokeObjectURL(objectUrl)
  }, [originalFile])

  function updateComparisonPosition(clientX: number) {
    const bounds = comparisonRef.current?.getBoundingClientRect()
    if (bounds === undefined || bounds.width === 0) {
      return
    }
    const percentage = ((clientX - bounds.left) / bounds.width) * 100
    setComparisonPosition(Math.min(100, Math.max(0, percentage)))
  }

  function beginDragging(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId)
    updateComparisonPosition(event.clientX)
  }

  function continueDragging(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      updateComparisonPosition(event.clientX)
    }
  }

  function stopDragging(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  function moveWithKeyboard(event: KeyboardEvent<HTMLDivElement>) {
    let nextPosition: number | null = null
    if (event.key === 'ArrowLeft') {
      nextPosition = comparisonPosition - KEYBOARD_STEP
    } else if (event.key === 'ArrowRight') {
      nextPosition = comparisonPosition + KEYBOARD_STEP
    } else if (event.key === 'Home') {
      nextPosition = 0
    } else if (event.key === 'End') {
      nextPosition = 100
    }
    if (nextPosition !== null) {
      event.preventDefault()
      setComparisonPosition(Math.min(100, Math.max(0, nextPosition)))
    }
  }

  const comparisonStyle = {
    '--comparison-position': `${comparisonPosition}%`,
    '--comparison-ratio': String(previewRatio),
  } as CSSProperties

  return (
    <section className="result-preview" aria-labelledby="result-preview-title">
      <div className="result-preview__heading">
        <div>
          <span className="eyebrow">Before / after comparison</span>
          <h3 id="result-preview-title">处理前后结果对比</h3>
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

      {loading && (
        <div className="result-preview__frame">
          <p>正在安全读取本地结果…</p>
        </div>
      )}
      {error && (
        <div className="result-preview__frame">
          <p className="submit-error">{error}</p>
        </div>
      )}
      {!loading && error === null && originalUrl !== null && previewUrl !== null && (
        <div
          ref={comparisonRef}
          className="result-comparison"
          style={comparisonStyle}
          role="slider"
          tabIndex={0}
          aria-label="拖动以比较原始目标场景图与模拟处理结果"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(comparisonPosition)}
          aria-valuetext={`原图显示 ${Math.round(comparisonPosition)}%，结果显示 ${Math.round(100 - comparisonPosition)}%`}
          onKeyDown={moveWithKeyboard}
          onPointerDown={beginDragging}
          onPointerMove={continueDragging}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
        >
          <img
            className="result-comparison__image"
            src={originalUrl}
            alt="原始目标场景图"
            draggable={false}
          />
          <div className="result-comparison__after" aria-hidden="true">
            <img
              className="result-comparison__image"
              src={previewUrl}
              alt=""
              draggable={false}
            />
          </div>
          <span className="result-comparison__label result-comparison__label--before">
            原图
          </span>
          <span className="result-comparison__label result-comparison__label--after">
            结果
          </span>
          <span className="result-comparison__divider" aria-hidden="true">
            <i>‹</i>
            <i>›</i>
          </span>
        </div>
      )}

      <p className="result-preview__hint">
        拖动分割线查看细节；聚焦对比区域后，也可使用方向键、Home 或 End 调整。
      </p>
      <p className="result-preview__notice">
        当前为模拟后端输出，不代表已经执行真实换脸；AI 编辑元数据始终保留。
      </p>
    </section>
  )
}

export default ResultPreview
