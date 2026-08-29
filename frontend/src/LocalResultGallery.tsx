import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  deleteTaskResult,
  listAvailableResults,
  taskResultUrl,
  type AvailableResult,
} from './api'

const RESULT_SYNC_INTERVAL_MS = 15_000
const EXPIRY_REFRESH_INTERVAL_MS = 60_000
const EXPIRY_WARNING_MS = 10 * 60 * 1_000

interface LocalResultGalleryProps {
  csrfToken: string | null
  enabled: boolean
  onResultsDeleted: (taskIds: string[]) => void
  refreshKey: string
}

function formattedCompletionTime(completedAt: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(completedAt))
}

function downloadName(result: AvailableResult): string {
  return `localface-simulation-${result.taskId.slice(0, 8)}.${
    result.outputFormat === 'jpeg' ? 'jpg' : 'png'
  }`
}

export default function LocalResultGallery({
  csrfToken,
  enabled,
  onResultsDeleted,
  refreshKey,
}: LocalResultGalleryProps) {
  const [results, setResults] = useState<AvailableResult[]>([])
  const [selected, setSelected] = useState<AvailableResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [confirmTarget, setConfirmTarget] = useState<'all' | string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const previewTriggerRef = useRef<HTMLElement | null>(null)
  const visibleResults = results.filter(
    (result) => Date.parse(result.expiresAt) > now,
  )
  const activeSelected =
    selected !== null &&
    visibleResults.some((result) => result.taskId === selected.taskId)
      ? selected
      : null

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    let stopped = false

    async function refreshResults(showLoading: boolean) {
      if (showLoading) {
        setLoading(true)
      }
      try {
        const available = await listAvailableResults(controller.signal)
        if (!stopped) {
          setResults(available)
          setError(null)
        }
      } catch (caught) {
        if (!stopped && !controller.signal.aborted) {
          setError(
            caught instanceof Error ? caught.message : '无法读取本地结果列表。',
          )
        }
      } finally {
        if (!stopped && showLoading) {
          setLoading(false)
        }
      }
    }

    void refreshResults(true)
    const interval = window.setInterval(
      () => void refreshResults(false),
      RESULT_SYNC_INTERVAL_MS,
    )
    return () => {
      stopped = true
      controller.abort()
      window.clearInterval(interval)
    }
  }, [enabled, refreshKey])

  useEffect(() => {
    const interval = window.setInterval(
      () => setNow(Date.now()),
      EXPIRY_REFRESH_INTERVAL_MS,
    )
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (activeSelected === null) {
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelected(null)
        setConfirmTarget(null)
        return
      }
      if (event.key !== 'Tab') {
        return
      }
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
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
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
      previewTriggerRef.current?.focus()
    }
  }, [activeSelected])

  function closePreview() {
    setSelected(null)
    setConfirmTarget(null)
  }

  function openPreview(result: AvailableResult) {
    previewTriggerRef.current = document.activeElement as HTMLElement | null
    setSelected(result)
  }

  async function clearResults(taskIds: string[]) {
    if (csrfToken === null || deleting || taskIds.length === 0) {
      return
    }
    setDeleting(true)
    setError(null)
    const outcomes = await Promise.allSettled(
      taskIds.map((taskId) => deleteTaskResult(taskId, csrfToken)),
    )
    const deletedIds = taskIds.filter(
      (_, index) => outcomes[index]?.status === 'fulfilled',
    )
    const failedCount = taskIds.length - deletedIds.length
    if (deletedIds.length > 0) {
      const deletedSet = new Set(deletedIds)
      setResults((current) =>
        current.filter((result) => !deletedSet.has(result.taskId)),
      )
      if (selected !== null && deletedSet.has(selected.taskId)) {
        setSelected(null)
      }
      onResultsDeleted(deletedIds)
    }
    if (failedCount > 0) {
      setError(
        failedCount === taskIds.length
          ? '无法清除本地图片与结果，请检查后端连接。'
          : `已清除 ${deletedIds.length} 项，另有 ${failedCount} 项清除失败。`,
      )
    }
    setConfirmTarget(null)
    setDeleting(false)
  }

  return (
    <section className="local-results" aria-labelledby="local-results-title">
      <div className="local-results__heading">
        <div>
          <span className="eyebrow">Local results</span>
          <h2 id="local-results-title">本地结果</h2>
        </div>
        <div className="local-results__heading-actions">
          <span className="local-results__count">{visibleResults.length}</span>
          {visibleResults.length > 0 && (
            <button
              className="local-results__clear-all"
              type="button"
              disabled={csrfToken === null || deleting}
              onClick={() => setConfirmTarget('all')}
            >
              清除全部
            </button>
          )}
        </div>
      </div>
      <p className="local-results__order">按生成时间倒序排列 · 最新结果在前</p>

      {confirmTarget === 'all' && (
        <div className="local-results__confirmation" role="alert">
          <p>
            将清除当前会话的全部本地结果及其关联上传副本，且无法恢复。已下载到其他位置的文件不会被删除。
          </p>
          <div>
            <button
              type="button"
              disabled={deleting}
              onClick={() => setConfirmTarget(null)}
            >
              取消
            </button>
            <button
              className="danger-action"
              type="button"
              disabled={deleting}
              onClick={() =>
                void clearResults(visibleResults.map((result) => result.taskId))
              }
            >
              {deleting ? '正在清除…' : '确认清除全部'}
            </button>
          </div>
        </div>
      )}

      {loading && visibleResults.length === 0 && (
        <p className="local-results__empty">正在读取当前会话的本地结果…</p>
      )}
      {!loading && error === null && visibleResults.length === 0 && (
        <p className="local-results__empty">当前会话还没有可用结果。</p>
      )}
      {error !== null && (
        <p className="local-results__error" role="alert">{error}</p>
      )}

      {visibleResults.length > 0 && (
        <div className="local-results__grid">
          {visibleResults.map((result) => {
            const expiresSoon =
              Date.parse(result.expiresAt) - now < EXPIRY_WARNING_MS
            return (
              <article className="local-result-card" key={result.taskId}>
                <button
                  className="local-result-card__preview"
                  type="button"
                  aria-label={`放大查看 ${formattedCompletionTime(result.completedAt)} 生成的结果`}
                  onClick={() => openPreview(result)}
                >
                  <img
                    src={taskResultUrl(result.taskId)}
                    alt=""
                    loading="lazy"
                  />
                </button>
                <time dateTime={result.completedAt}>
                  {formattedCompletionTime(result.completedAt)}
                </time>
                {expiresSoon && (
                  <span className="local-result-card__expiry">
                    剩余时间不足 10 分钟
                  </span>
                )}
              </article>
            )
          })}
        </div>
      )}

      {activeSelected !== null &&
        createPortal(
          <div
            className="result-lightbox"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closePreview()
              }
            }}
          >
            <section
              ref={dialogRef}
              className="result-lightbox__dialog"
              role="dialog"
              aria-modal="true"
              aria-label="本地结果大图"
            >
              <button
                ref={closeButtonRef}
                className="result-lightbox__close"
                type="button"
                aria-label="关闭大图"
                onClick={closePreview}
              >
                ×
              </button>
              <div className="result-lightbox__image">
                <img
                  src={taskResultUrl(activeSelected.taskId)}
                  alt={`${formattedCompletionTime(activeSelected.completedAt)} 生成的处理结果`}
                />
              </div>
              {confirmTarget === activeSelected.taskId ? (
                <div
                  className="result-lightbox__controls result-lightbox__confirmation"
                  role="alert"
                >
                  <span>将同时清除关联上传副本，且无法恢复。</span>
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={() => setConfirmTarget(null)}
                  >
                    取消
                  </button>
                  <button
                    className="danger-action"
                    type="button"
                    disabled={deleting}
                    onClick={() => void clearResults([activeSelected.taskId])}
                  >
                    {deleting ? '正在清除…' : '确认清除'}
                  </button>
                </div>
              ) : (
                <div className="result-lightbox__controls result-lightbox__actions">
                  <button
                    className="result-clear"
                    type="button"
                    disabled={csrfToken === null || deleting}
                    onClick={() => setConfirmTarget(activeSelected.taskId)}
                  >
                    清除此结果
                  </button>
                  <a
                    className="result-download"
                    href={taskResultUrl(activeSelected.taskId)}
                    download={downloadName(activeSelected)}
                  >
                    下载结果
                  </a>
                </div>
              )}
            </section>
          </div>,
          document.body,
        )}
    </section>
  )
}
