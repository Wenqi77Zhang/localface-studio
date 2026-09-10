import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'
import { useTaskResults } from './useTaskResults'
import { type ResultVariant } from './api'

interface ResultPreviewProps {
  taskId: string
  expiresAt: string
  originalFile: File
  outputFormat: 'png' | 'jpeg'
  previewRatio: number
}

const DEFAULT_COMPARISON_POSITION = 50
const KEYBOARD_STEP = 2

function ResultPreview({
  taskId,
  expiresAt,
  originalFile,
  outputFormat,
  previewRatio,
}: ResultPreviewProps) {
  const { error, loading, urls, artifacts } = useTaskResults(taskId, expiresAt)
  const [selectedVariant, setSelectedVariant] = useState<ResultVariant>('enhanced')
  const [compareBase, setCompareBase] = useState(false)
  const variant = artifacts?.variants.includes(selectedVariant) ? selectedVariant :
    artifacts?.variants[0] ?? 'final'
  const previewUrl = urls[variant] ?? null
  const labels: Record<ResultVariant, string> = { base: '基础版', enhanced: '色彩优化版', final: '结果' }
  const simulated = artifacts?.workflowBackend === 'simulation'
  const downloadName = `localface-${simulated ? 'simulation-' : ''}${variant}.${outputFormat === 'jpeg' ? 'jpg' : 'png'}`
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
    // Object URLs and comparison position synchronize with a new target File.
    // oxlint-disable-next-line react/set-state-in-effect
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
  const comparisonUrl = compareBase && variant === 'enhanced' ? urls.base ?? originalUrl : originalUrl
  const comparisonLabel = compareBase && variant === 'enhanced' ? '基础版' : '原图'

  return (
    <section className="result-preview" aria-labelledby="result-preview-title">
      <div className="result-preview__heading">
        <div>
          <span className="eyebrow">Before / after comparison</span>
          <h3 id="result-preview-title">{simulated ? '模拟流程结果（未换脸）' : '换脸结果与对比'}</h3>
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
              download={downloadName}
            >
              下载{outputFormat === 'jpeg' ? ' JPEG' : ' PNG'}结果
            </a>
          </div>
        )}
      </div>

      {artifacts !== null && (
        <div className="result-variants" aria-label="结果版本与对比方式">
          <div className="result-variants__tabs" role="group" aria-label="选择结果版本">
            {artifacts.variants.map((item) => (
              <button key={item} type="button" aria-pressed={variant === item}
                onClick={() => setSelectedVariant(item)}>{labels[item]}</button>
            ))}
          </div>
          {variant === 'enhanced' && urls.base !== undefined && (
            <label><input type="checkbox" checked={compareBase}
              onChange={(event) => setCompareBase(event.currentTarget.checked)} />
              与基础版对比（未勾选时与原图对比）</label>
          )}
          <p>每个版本可独立下载；色彩优化是局部颜色校正，不会凭空修复五官或提高模型原生分辨率。</p>
          {typeof artifacts.metrics.duration_ms === 'number' && (
            <p className="result-metrics">本次处理 {(artifacts.metrics.duration_ms / 1000).toFixed(2)} 秒
              {typeof artifacts.metrics.rss_peak_mb === 'number' &&
                ` · 进程内存采样峰值 ${Math.round(artifacts.metrics.rss_peak_mb)} MB`}
            </p>
          )}
        </div>
      )}

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
          aria-label={`拖动以比较${comparisonLabel}与${labels[variant]}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(comparisonPosition)}
          aria-valuetext={`${comparisonLabel}显示 ${Math.round(comparisonPosition)}%，${labels[variant]}显示 ${Math.round(100 - comparisonPosition)}%`}
          onKeyDown={moveWithKeyboard}
          onPointerDown={beginDragging}
          onPointerMove={continueDragging}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
        >
          <img
            className="result-comparison__image"
            src={comparisonUrl ?? undefined}
            alt={comparisonLabel}
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
            {comparisonLabel}
          </span>
          <span className="result-comparison__label result-comparison__label--after">
            {labels[variant]}
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
                    download={downloadName}
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
