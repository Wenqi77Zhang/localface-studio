import { useEffect, useState } from 'react'

const MAXIMUM_IMAGE_BYTES = 25 * 1024 * 1024
const ACCEPTED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

interface PhotoPickerProps {
  detail: string
  file: File | null
  label: string
  onChange: (file: File | null) => void
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
  detail,
  file,
  label,
  onChange,
}: PhotoPickerProps) {
  const [error, setError] = useState<string | null>(null)
  const previewUrl = usePreviewUrl(file)

  function chooseFile(candidate: File | undefined) {
    if (candidate === undefined) {
      return
    }
    const validationError = validateImage(candidate)
    setError(validationError)
    if (validationError === null) {
      onChange(candidate)
    }
  }

  return (
    <section className={`photo-picker${file ? ' photo-picker--ready' : ''}`}>
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
              onChange(null)
            }}
          >
            移除
          </button>
        )}
      </div>

      <label className="photo-picker__surface">
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => {
            chooseFile(event.currentTarget.files?.[0])
            event.currentTarget.value = ''
          }}
        />
        {previewUrl ? (
          <img src={previewUrl} alt={`${label}本地预览`} />
        ) : (
          <span>
            <b>选择图片</b>
            <small>PNG / JPEG / 静态 WebP · 最大 25 MB</small>
          </span>
        )}
      </label>

      <p className={error ? 'field-message field-message--error' : 'field-message'}>
        {error ?? (file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · 仅在本机预览` : '尚未选择')}
      </p>
    </section>
  )
}
