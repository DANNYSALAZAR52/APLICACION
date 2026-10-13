// Error normalizado: mensaje en español, código estable y, si existe, id de seguimiento.

export interface FieldError {
  campo: string
  mensaje: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly fields: FieldError[]

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
    fields: FieldError[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.fields = fields
  }

  get isAuth(): boolean {
    return this.status === 401
  }
}

interface ErrorBody {
  error?: {
    codigo?: unknown
    mensaje?: unknown
    id_solicitud?: unknown
    campos?: unknown
  }
}

const isFieldError = (value: unknown): value is FieldError =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as FieldError).campo === 'string' &&
  typeof (value as FieldError).mensaje === 'string'

/** Convierte cualquier respuesta de error (o cuerpo inesperado) en un `ApiError` seguro. */
export function parseApiError(status: number, body: unknown): ApiError {
  const error = (body as ErrorBody | null)?.error
  const code = typeof error?.codigo === 'string' ? error.codigo : 'ERROR_DESCONOCIDO'
  const message =
    typeof error?.mensaje === 'string' && error.mensaje
      ? error.mensaje
      : 'No se pudo completar la operación. Intente de nuevo.'
  const requestId = typeof error?.id_solicitud === 'string' ? error.id_solicitud : null
  const fields = Array.isArray(error?.campos) ? error.campos.filter(isFieldError) : []
  return new ApiError(status, code, message, requestId, fields)
}

export const networkError = (): ApiError =>
  new ApiError(0, 'SIN_CONEXION', 'No se pudo conectar con el servidor. Revise su conexión.')
