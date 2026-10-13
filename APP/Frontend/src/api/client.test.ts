import { describe, expect, it, vi } from 'vitest'

import { makeSession, makeUser } from '../test/fixtures'
import { ApiClient } from './client'
import { ApiError, parseApiError } from './errors'

const json = (status: number, body: unknown, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...extra },
  })

const session = makeSession(makeUser('management'))

describe('parseApiError', () => {
  it('lee código, mensaje, id y campos', () => {
    const error = parseApiError(422, {
      error: {
        codigo: 'SOLICITUD_INVALIDA',
        mensaje: 'La solicitud contiene datos no válidos.',
        id_solicitud: 'abc123',
        campos: [{ campo: 'slug', mensaje: 'Campo obligatorio.' }, { raro: 1 }],
      },
    })
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('SOLICITUD_INVALIDA')
    expect(error.requestId).toBe('abc123')
    expect(error.fields).toEqual([{ campo: 'slug', mensaje: 'Campo obligatorio.' }])
  })

  it.each([null, undefined, 'texto', 42, { error: 'x' }, { error: { mensaje: 5 } }])(
    'un cuerpo inesperado (%j) da un mensaje genérico en español sin romper',
    (body) => {
      const error = parseApiError(500, body)
      expect(error.message).toMatch(/No se pudo completar/)
      expect(error.code).toBe('ERROR_DESCONOCIDO')
    },
  )
})

describe('ApiClient', () => {
  it('login guarda el token solo en memoria y lo envía después', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(200, session))
      .mockResolvedValueOnce(json(200, { ok: true }))
    const client = new ApiClient('/api/v1', fetchMock)
    await client.login({ tenant_slug: 'empresa-demo-a', username: 'u', password: 'p' })
    await client.dashboard()

    const [, loginInit] = fetchMock.mock.calls[0]!
    expect(loginInit.headers.Authorization).toBeUndefined() // el login no envía token
    expect(loginInit.credentials).toBe('include')
    const [url, dashInit] = fetchMock.mock.calls[1]!
    expect(url).toBe('/api/v1/capacity/dashboard')
    expect(dashInit.headers.Authorization).toBe('Bearer token-de-prueba')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('ante un 401 refresca una vez y repite la solicitud', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401, { error: { codigo: 'AUTENTICACION_REQUERIDA', mensaje: 'x' } }))
      .mockResolvedValueOnce(json(200, { ...session, access_token: 'nuevo-token' }))
      .mockResolvedValueOnce(json(200, [{ slug: 'a' }]))
    const client = new ApiClient('/api/v1', fetchMock)
    client.setAccessToken('viejo')
    const result = await client.tenants()
    expect(result).toEqual([{ slug: 'a' }])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1]![0]).toBe('/api/v1/auth/refresh')
    expect(fetchMock.mock.calls[2]![1].headers.Authorization).toBe('Bearer nuevo-token')
  })

  it('si el refresco falla avisa que la sesión terminó y lanza el 401', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401, { error: { codigo: 'AUTENTICACION_REQUERIDA', mensaje: 'Debe iniciar sesión.' } }))
      .mockResolvedValueOnce(json(401, { error: { codigo: 'AUTENTICACION_INVALIDA', mensaje: 'La sesión expiró.' } }))
    const client = new ApiClient('/api/v1', fetchMock)
    const ended = vi.fn()
    client.onSessionEnded = ended
    await expect(client.tenants()).rejects.toMatchObject({ status: 401 })
    expect(ended).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2) // no entra en bucle
  })

  it('refrescos simultáneos comparten una sola llamada (no rota el token dos veces)', async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(json(200, session)), 5)),
    )
    const client = new ApiClient('/api/v1', fetchMock)
    const [a, b, c] = await Promise.all([
      client.refreshSession(),
      client.refreshSession(),
      client.refreshSession(),
    ])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(a).toBe(b)
    expect(b).toBe(c)
    await client.refreshSession() // pasado el primero, se puede volver a pedir
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('un fallo de red se convierte en un error entendible', async () => {
    const client = new ApiClient('/api/v1', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    await expect(client.login({ tenant_slug: null, username: 'u', password: 'p' })).rejects.toMatchObject({
      code: 'SIN_CONEXION',
      message: expect.stringContaining('No se pudo conectar'),
    })
  })

  it('la cancelación (AbortError) no se disfraza de error de red', async () => {
    const abort = new DOMException('cancelado', 'AbortError')
    const client = new ApiClient('/api/v1', vi.fn().mockRejectedValue(abort))
    client.setAccessToken('t')
    await expect(client.dashboard()).rejects.toBe(abort)
  })

  it('errores del servidor llegan normalizados', async () => {
    const client = new ApiClient(
      '/api/v1',
      vi.fn().mockResolvedValue(
        json(403, { error: { codigo: 'EMPRESA_SUSPENDIDA', mensaje: 'La empresa está suspendida.', id_solicitud: 'r1' } }),
      ),
    )
    client.setAccessToken('t')
    await expect(client.dashboard()).rejects.toMatchObject({
      status: 403,
      code: 'EMPRESA_SUSPENDIDA',
      requestId: 'r1',
    })
  })

  it('logout limpia el token aunque el servidor falle', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(500, {}))
    const client = new ApiClient('/api/v1', fetchMock)
    client.setAccessToken('t')
    await expect(client.logout()).rejects.toBeInstanceOf(ApiError)
    fetchMock.mockResolvedValue(json(200, []))
    await client.tenants().catch(() => undefined)
    const last = fetchMock.mock.calls.at(-1)![1]
    expect(last.headers.Authorization).toBeUndefined()
  })

  it('codifica el slug en la URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { slug: 'x' }))
    const client = new ApiClient('/api/v1', fetchMock)
    client.setAccessToken('t')
    await client.suspendTenant('a/../b')
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/tenants/a%2F..%2Fb/suspend')
  })
})
