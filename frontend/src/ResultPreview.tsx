import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

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
  const [inspectionOpen, setInspectionOpen] = useState(false)
  const comparisonRef = useRef<HTMLDivElement>(null)
  const inspectionButtonRef = useRef<HTMLButtonElement>(null)
  const inspectionDialogRef = useRef<HTMLElement>(null)
  const inspectionCloseRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const objectUrl = URL.createObjectURL(originalFile)
    setOriginalUrl(objectUrl)
    setComparisonPosition(DEFAULT_COMPARISON_POSITION)
    return () => URL.revokeObjectURL(objectUrl)
  }, [originalFile])

  useEffect(() => {
    if (!inspectionOpen) {
      return
    }
    const inspectionTrigger = inspectionButtonRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    inspectionCloseRef.current?.focus()
    const handleKeyboard = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setInspectionOpen(false)
        return
      }
      if (event.key !== 'Tab') {
        return
      }
      const focusable = inspectionDialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
      )
      if (focusable === undefined || focusable.length === 0) {
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }
    window.addEventListener('keydown', handleKeyboard)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyboard)
      inspectionTrigger?.focus()
    }
  }, [inspectionOpen])

  useEffect(() => {
    setInspectionOpen(false)
  }, [previewUrl])

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
          <div className="result-preview__actions">
            <button
              ref={inspectionButtonRef}
              className="result-inspect"
              type="button"
              onClick={() => setInspectionOpen(true)}
            >
              放大质检
            </button>
            <a
              className="result-download"
              href={previewUrl}
              download={`localface-simulation.${outputFormat === 'jpeg' ? 'jpg' : 'png'}`}
            >
              下载{outputFormat === 'jpeg' ? ' JPEG' : ' PNG'}结果
            </a>
          </div>
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
        自动指标不能可靠识别重影或纹理破碎。下载前请使用“放大质检”检查眼睛、牙齿、发际线与脸部轮廓；AI
        编辑元数据始终保留。
      </p>

      {inspectionOpen && previewUrl !== null &&
        createPortal(
          <div
            className="inspection-lightbox"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setInspectionOpen(false)
              }
            }}
          >
            <section
              ref={inspectionDialogRef}
              className="inspection-lightbox__dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="inspection-title"
              aria-describedby="inspection-guidance"
            >
              <header className="inspection-lightbox__header">
                <div>
                  <span className="eyebrow">Manual quality gate</span>
                  <h4 id="inspection-title">结果放大质检</h4>
                </div>
                <button
                  ref={inspectionCloseRef}
                  className="result-lightbox__close"
                  type="button"
                  aria-label="关闭放大质检"
                  onClick={() => setInspectionOpen(false)}
                >
                  ×
                </button>
              </header>
              <div className="inspection-lightbox__image">
                <img src={previewUrl} alt="等待人工放大检查的处理结果" />
              </div>
              <div className="inspection-lightbox__footer">
                <p id="inspection-guidance">
                  重点检查：双眼是否重影，牙齿与嘴唇是否破碎，发际线与脸部轮廓是否出现接缝，肤色是否突变。
                </p>
                <div className="inspection-lightbox__actions">
                  <a
                    className="result-inspect"
                    href={previewUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    新窗口查看原图
                  </a>
                  <a
                    className="result-download"
                    href={previewUrl}
                    download={`localface-simulation.${outputFormat === 'jpeg' ? 'jpg' : 'png'}`}
                  >
                    下载结果
                  </a>
                </div>
              </div>
            </section>
          </div>,
          document.body,
        )}
    </section>
  )
}

export default ResultPreview
