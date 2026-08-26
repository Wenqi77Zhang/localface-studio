import { type CSSProperties, useEffect, useId, useState } from 'react'
import type { DetectedFace, FaceDetectionRevision } from './api'
import type { FaceDetectionState } from './useFaceDetection'

const MAXIMUM_IMAGE_BYTES = 25 * 1024 * 1024
const ACCEPTED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])
const MINIMUM_PREVIEW_RATIO = 3 / 4
const MAXIMUM_PREVIEW_RATIO = 16 / 9
const MINIMUM_RELIABLE_FACE_PIXELS = 96
const CLOSE_UP_WIDTH_RATIO = 0.45
const CLOSE_UP_HEIGHT_RATIO = 0.55
const EDGE_MARGIN_RATIO = 0.02

interface PhotoPickerProps {
  attentionMessage: string | null
  detail: string
  file: File | null
  detection: FaceDetectionState
  label: string
  onChange: (file: File | null) => void
  onRatioChange: (ratio: number | null) => void
  onSelectFace: (detectionId: string) => void
  previewRatio: number
}

function validateImage(file: File): string | null {
  if (!ACCEPTED_IMAGE_TYPES.has(file.type)) {
    return '仅支持 PNG、JPEG 和静态 WebP 图片。'
  }
  if (file.size < 1) {
    return '图片不能为空。'
  }
  if (file.size > MAXIMUM_IMAGE_BYTES) {
    return '单张图片不能超过 25 MB。'
  }
  return null
}

function usePreviewUrl(file: File | null): string | null {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  useEffect(() => {
    if (file === null) {
      setPreviewUrl(null)
      return
    }
    const objectUrl = URL.createObjectURL(file)
    setPreviewUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])

  return previewUrl
}

export default function PhotoPicker({
  attentionMessage,
  detection,
  detail,
  file,
  label,
  onChange,
  onRatioChange,
  onSelectFace,
  previewRatio,
}: PhotoPickerProps) {
  const [error, setError] = useState<string | null>(null)
  const inputId = useId()
  const previewUrl = usePreviewUrl(file)
  const previewStyle = { '--preview-ratio': String(previewRatio) } as CSSProperties
  const revision = detection.status === 'ready' ? detection.revision : null
  const selecting = detection.status === 'ready' && detection.selecting
  const detectionMessage = describeDetection(detection)
  const qualityAdvisory = describeQualityAdvisory(detection)
  const detectionFailed =
    detection.status === 'error' ||
    (detection.status === 'ready' && detection.revision.faces.length === 0)
  const messageClassName =
    error || attentionMessage || detectionFailed
      ? 'field-message field-message--error'
      : qualityAdvisory !== null
        ? 'field-message field-message--warning'
        : 'field-message'

  function chooseFile(candidate: File | undefined) {
    if (candidate === undefined) {
      return
    }
    const validationError = validateImage(candidate)
    setError(validationError)
    if (validationError === null) {
      onRatioChange(null)
      onChange(candidate)
    }
  }

  return (
    <section
      className={[
        'photo-picker',
        file ? 'photo-picker--ready' : '',
        attentionMessage ? 'photo-picker--attention' : '',
        detectionFailed ? 'photo-picker--detection-error' : '',
      ].join(' ')}
    >
      <div className="photo-picker__heading">
        <div>
          <strong>{label}</strong>
          <span>{detail}</span>
        </div>
        {file && (
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setError(null)
              onRatioChange(null)
              onChange(null)
            }}
          >
            移除
          </button>
        )}
      </div>

      <div className="photo-picker__surface" style={previewStyle}>
        <input
          id={inputId}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => {
            chooseFile(event.currentTarget.files?.[0])
            event.currentTarget.value = ''
          }}
        />
        <label className="photo-picker__select" htmlFor={inputId}>
          {previewUrl ? (
            <img
              src={previewUrl}
              alt={`${label}本地预览`}
              onLoad={(event) => {
                const image = event.currentTarget
                const naturalRatio = image.naturalWidth / image.naturalHeight
                onRatioChange(
                  Math.min(
                    MAXIMUM_PREVIEW_RATIO,
                    Math.max(MINIMUM_PREVIEW_RATIO, naturalRatio),
                  ),
                )
              }}
            />
          ) : (
            <span>
              <b>选择图片</b>
              <small>PNG / JPEG / 静态 WebP · 最大 25 MB</small>
            </span>
          )}
        </label>
        {revision !== null && revision.faces.length > 0 && (
          <div className="face-overlay" aria-label={`${label}人物选择`}>
            {revision.faces.map((face) => (
              <button
                key={face.detectionId}
                type="button"
                className={[
                  'face-box',
                  revision.selectedDetectionId === face.detectionId
                    ? 'face-box--selected'
                    : '',
                ].join(' ')}
                style={faceBoxStyle(face, revision, previewRatio)}
                aria-label={`选择人物 ${face.ordinal}`}
                aria-pressed={revision.selectedDetectionId === face.detectionId}
                disabled={selecting}
                onClick={() => onSelectFace(face.detectionId)}
              >
                <span>{face.ordinal}</span>
              </button>
            ))}
          </div>
        )}
        {detection.status === 'detecting' && (
          <span className="detection-badge" role="status">正在检测人物…</span>
        )}
      </div>

      <p
        className={messageClassName}
        aria-live="polite"
      >
        {error ??
          attentionMessage ??
          qualityAdvisory ??
          detectionMessage ??
          (file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · 仅在本机预览` : '尚未选择')}
      </p>
    </section>
  )
}

function describeQualityAdvisory(state: FaceDetectionState): string | null {
  if (state.status !== 'ready' || state.revision.selectedDetectionId === null) {
    return null
  }
  const revision = state.revision
  const face = revision.faces.find(
    (candidate) => candidate.detectionId === revision.selectedDetectionId,
  )
  if (face === undefined) {
    return null
  }
  const risks: string[] = []
  const widthRatio = face.box.width / revision.width
  const heightRatio = face.box.height / revision.height
  if (Math.min(face.box.width, face.box.height) < MINIMUM_RELIABLE_FACE_PIXELS) {
    risks.push('人脸像素较少')
  }
  if (widthRatio > CLOSE_UP_WIDTH_RATIO || heightRatio > CLOSE_UP_HEIGHT_RATIO) {
    risks.push('人脸属于超近景')
  }
  const horizontalMargin = revision.width * EDGE_MARGIN_RATIO
  const verticalMargin = revision.height * EDGE_MARGIN_RATIO
  if (
    face.box.x < horizontalMargin ||
    face.box.y < verticalMargin ||
    face.box.x + face.box.width > revision.width - horizontalMargin ||
    face.box.y + face.box.height > revision.height - verticalMargin
  ) {
    risks.push('人脸接近画面边缘')
  }
  if (risks.length === 0) {
    return null
  }
  return `质检提示：${risks.join('、')}，更容易出现模糊、错位或融合接缝；生成后请务必放大检查。`
}

function describeDetection(state: FaceDetectionState): string | null {
  if (state.status === 'detecting') {
    return '正在使用本地模型检测人物…'
  }
  if (state.status === 'error') {
    return state.message
  }
  if (state.status === 'blocked') {
    return state.message
  }
  if (state.status !== 'ready') {
    return null
  }
  if (state.revision.faces.length === 0) {
    return '未检测到人脸，请更换清晰、正面或人物更大的图片。'
  }
  if (state.selecting) {
    return '正在保存人物选择…'
  }
  if (state.revision.selectionRequired) {
    return `检测到 ${state.revision.faces.length} 人，请点击框选一名人物。`
  }
  const selectedOrdinal = state.revision.faces.find(
    (face) => face.detectionId === state.revision.selectedDetectionId,
  )?.ordinal
  return selectedOrdinal === undefined
    ? '人物检测已完成。'
    : `已选择人物 ${selectedOrdinal}。`
}

function faceBoxStyle(
  face: DetectedFace,
  revision: FaceDetectionRevision,
  previewRatio: number,
): CSSProperties {
  const imageRatio = revision.width / revision.height
  let displayedWidth = 100
  let displayedHeight = 100
  let offsetX = 0
  let offsetY = 0
  if (imageRatio > previewRatio) {
    displayedHeight = (previewRatio / imageRatio) * 100
    offsetY = (100 - displayedHeight) / 2
  } else {
    displayedWidth = (imageRatio / previewRatio) * 100
    offsetX = (100 - displayedWidth) / 2
  }
  return {
    left: `${offsetX + (face.box.x / revision.width) * displayedWidth}%`,
    top: `${offsetY + (face.box.y / revision.height) * displayedHeight}%`,
    width: `${(face.box.width / revision.width) * displayedWidth}%`,
    height: `${(face.box.height / revision.height) * displayedHeight}%`,
  }
}
