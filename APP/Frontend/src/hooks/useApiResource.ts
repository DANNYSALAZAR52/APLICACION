import { useCallback, useEffect, useRef, useState } from 'react'

export type ResourceState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'success'; data: T; loadedAt: number }

/**
 * Carga un recurso y cancela la consulta anterior si se vuelve a pedir o se sale de la pantalla,
 * para que una respuesta obsoleta nunca pise a una más reciente.
 */
export function useApiResource<T>(loader: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' })
  const controller = useRef<AbortController | null>(null)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const load = useCallback(() => {
    controller.current?.abort()
    const next = new AbortController()
    controller.current = next
    setState({ status: 'loading' })
    loaderRef
      .current(next.signal)
      .then((data) => {
        if (!next.signal.aborted) setState({ status: 'success', data, loadedAt: Date.now() })
      })
      .catch((error: unknown) => {
        if (next.signal.aborted) return
        setState({ status: 'error', error })
      })
  }, [])

  useEffect(() => {
    load()
    return () => controller.current?.abort()
  }, [load])

  return { state, reload: load }
}
