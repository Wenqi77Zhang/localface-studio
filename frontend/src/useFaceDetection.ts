import { useEffect, useMemo, useRef, useState } from 'react'
import {
  detectFaces,
  selectDetectedFace,
  type FaceDetectionRevision,
  type FaceImageRole,
} from './api'

export type FaceDetectionState =
  | { status: 'idle' }
  | { message: string; status: 'blocked' }
  | { status: 'detecting' }
  | { message: string; status: 'error' }
  | { revision: FaceDetectionRevision; selecting: boolean; status: 'ready' }

export function useFaceDetection(input: {
  csrfToken: string | null
  detectorId: string
  file: File | null
  researchLicenseAccepted: boolean
  role: FaceImageRole
}) {
  const [state, setState] = useState<FaceDetectionState>({ status: 'idle' })
  const selectionController = useRef<AbortController | null>(null)
  const unavailableState = useMemo<FaceDetectionState | null>(
    () =>
      input.file === null
        ? { status: 'idle' }
        : input.detectorId === 'scrfd-insightface-research' &&
            !input.researchLicenseAccepted
          ? {
              status: 'blocked',
              message: '请先在高级设置中确认 SCRFD 非商业研究限制。',
            }
          : input.csrfToken === null
            ? { status: 'error', message: '本地会话尚未就绪，暂时无法检测人物。' }
            : null,
    [
      input.csrfToken,
      input.detectorId,
      input.file,
      input.researchLicenseAccepted,
    ],
  )

  useEffect(() => {
    selectionController.current?.abort()
    if (unavailableState !== null || input.file === null || input.csrfToken === null) {
      return
    }
    const controller = new AbortController()
    // This transition is the start of the external detection request synchronized here.
    // oxlint-disable-next-line react/set-state-in-effect
    setState({ status: 'detecting' })
    void detectFaces({
      csrfToken: input.csrfToken,
      detectorId: input.detectorId,
      file: input.file,
      researchLicenseAccepted: input.researchLicenseAccepted,
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
  }, [
    input.csrfToken,
    input.detectorId,
    input.file,
    input.researchLicenseAccepted,
    input.role,
    unavailableState,
  ])

  async function select(detectionId: string) {
    if (
      input.csrfToken === null ||
      unavailableState !== null ||
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

  return { state: unavailableState ?? state, select }
}
