import { useEffect, useRef, useState } from 'react'
import {
  detectFaces,
  selectDetectedFace,
  type FaceDetectionRevision,
  type FaceImageRole,
} from './api'

export type FaceDetectionState =
  | { status: 'idle' }
  | { status: 'detecting' }
  | { message: string; status: 'error' }
  | { revision: FaceDetectionRevision; selecting: boolean; status: 'ready' }

export function useFaceDetection(input: {
  csrfToken: string | null
  detectorId: string
  file: File | null
  role: FaceImageRole
}) {
  const [state, setState] = useState<FaceDetectionState>({ status: 'idle' })
  const selectionController = useRef<AbortController | null>(null)

  useEffect(() => {
    selectionController.current?.abort()
    if (input.file === null) {
      setState({ status: 'idle' })
      return
    }
    if (input.csrfToken === null) {
      setState({ status: 'error', message: '本地会话尚未就绪，暂时无法检测人物。' })
      return
    }
    const controller = new AbortController()
    setState({ status: 'detecting' })
    void detectFaces({
      csrfToken: input.csrfToken,
      detectorId: input.detectorId,
      file: input.file,
      role: input.role,
      signal: controller.signal,
    })
      .then((revision) => {
        setState({ status: 'ready', revision, selecting: false })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            message: error instanceof Error ? error.message : '人物检测失败。',
          })
        }
      })
    return () => controller.abort()
  }, [input.csrfToken, input.detectorId, input.file, input.role])

  async function select(detectionId: string) {
    if (
      input.csrfToken === null ||
      state.status !== 'ready' ||
      state.selecting
    ) {
      return
    }
    selectionController.current?.abort()
    const controller = new AbortController()
    selectionController.current = controller
    const revisionId = state.revision.revisionId
    setState({ ...state, selecting: true })
    try {
      const revision = await selectDetectedFace({
        csrfToken: input.csrfToken,
        detectionId,
        revisionId,
        signal: controller.signal,
      })
      setState((current) =>
        current.status === 'ready' && current.revision.revisionId === revisionId
          ? { status: 'ready', revision, selecting: false }
          : current,
      )
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : '无法保存人物选择。',
        })
      }
    }
  }

  useEffect(
    () => () => {
      selectionController.current?.abort()
    },
    [],
  )

  return { state, select }
}
