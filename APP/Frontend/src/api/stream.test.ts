import { describe, expect, it, vi } from 'vitest'

import { ApiClient, readEventStream } from './client'
import type { RoutingSnapshot } from './types'

const encoder = new TextEncoder()

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

const collect = async (...chunks: string[]) => {
  const events: [string, string][] = []
  await readEventStream(streamOf(...chunks), (event, data) => events.push([event, data]))
  return events
}

describe('lector de eventos del servidor (SSE)', () => {
  it('entrega cada evento con su nombre y sus datos', async () => {
    expect(await collect('event: snapshot\ndata: {"a":1}\n\nevent: end\ndata: {"reason":"renew"}\n\n')).toEqual([
      ['snapshot', '{"a":1}'],
      ['end', '{"reason":"renew"}'],
    ])
  })

  it('ignora los comentarios de keep-alive', async () => {
    expect(await collect(': ping\n\nevent: snapshot\ndata: 1\n\n: ping\n\n')).toEqual([['snapshot', '1']])
  })

  it('reconstruye un evento partido en varios fragmentos, incluso en mitad de un carácter', async () => {
    const bytes = encoder.encode('event: snapshot\ndata: "señal"\n\n')
    const cut = bytes.indexOf(0xc3) + 1 // parte la "ñ" en dos bytes
    const events: [string, string][] = []
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut))
        controller.enqueue(bytes.slice(cut))
        controller.close()
      },
    })
    await readEventStream(body, (e, d) => events.push([e, d]))
    expect(events).toEqual([['snapshot', '"señal"']])
  })

  it('une los datos de varias líneas y no emite bloques sin datos', async () => {
    expect(await collect('event: snapshot\ndata: a\ndata: b\n\nevent: nada\n\n')).toEqual([['snapshot', 'a\nb']])
  })
})

const snapshot = (minute: number) => ({ clock: { minute } }) as unknown as RoutingSnapshot
const sse = (minute: number) => `event: snapshot\ndata: ${JSON.stringify(snapshot(minute))}\n\n`
const okStream = (...chunks: string[]) =>
  new Response(streamOf(...chunks), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })

describe('ApiClient.watchTower', () => {
  it('entrega los estados, envía el token y pide text/event-stream', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(okStream(sse(300), sse(302)))
      .mockImplementation(() => new Promise(() => undefined))
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    client.setAccessToken('tok')
    const seen: number[] = []
    const stop = client.watchTower((s) => seen.push(s.clock.minute), vi.fn(), 1)
    await vi.waitFor(() => expect(seen).toEqual([300, 302]))
    stop()
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/routing/stream')
    const headers = init.headers as Record<string, string>
    expect(headers.Accept).toBe('text/event-stream')
    expect(headers.Authorization).toBe('Bearer tok')
  })

  it('se reconecta solo cuando el servidor cierra el flujo', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(okStream(sse(300), 'event: end\ndata: {"reason":"renew"}\n\n'))
      .mockResolvedValueOnce(okStream(sse(310)))
      .mockImplementation(() => new Promise(() => undefined))
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    const seen: number[] = []
    const stop = client.watchTower((s) => seen.push(s.clock.minute), vi.fn(), 1)
    await vi.waitFor(() => expect(seen).toEqual([300, 310]))
    stop()
  })

  it('ante un 401 renueva la sesión una vez y reintenta', async () => {
    const session = {
      access_token: 'nuevo',
      token_type: 'bearer',
      expires_at: 'x',
      user: { id: 'u', username: 'd', display_name: 'D', role: 'dispatcher', tenant_slug: 'a', tenant_name: 'A', permissions: [] },
    }
    const fetchImpl = vi.fn((url: string) => {
      if (url.endsWith('/auth/refresh')) return Promise.resolve(Response.json(session))
      const calls = fetchImpl.mock.calls.filter(([u]) => String(u).endsWith('/routing/stream')).length
      if (calls === 1) return Promise.resolve(new Response(null, { status: 401 }))
      return calls === 2 ? Promise.resolve(okStream(sse(305))) : new Promise<Response>(() => undefined)
    })
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    client.setAccessToken('vencido')
    const seen: number[] = []
    const stop = client.watchTower((s) => seen.push(s.clock.minute), vi.fn(), 1)
    await vi.waitFor(() => expect(seen).toEqual([305]))
    stop()
    const retry = fetchImpl.mock.calls.filter(([u]) => String(u).endsWith('/routing/stream'))[1] as unknown as [string, RequestInit]
    expect((retry[1].headers as Record<string, string>).Authorization).toBe('Bearer nuevo')
  })

  it('tras tres fallos seguidos avisa que no está disponible y deja de intentar', async () => {
    const fetchImpl = vi.fn(() => Promise.reject(new Error('sin red')))
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    const unavailable = vi.fn()
    client.watchTower(vi.fn(), unavailable, 1)
    await vi.waitFor(() => expect(unavailable).toHaveBeenCalledTimes(1))
    expect(fetchImpl).toHaveBeenCalledTimes(3)
  })

  it('un error HTTP (por ejemplo 403) cuenta como fallo y no entrega datos', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response('{}', { status: 403 })))
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    const seen = vi.fn()
    const unavailable = vi.fn()
    client.watchTower(seen, unavailable, 1)
    await vi.waitFor(() => expect(unavailable).toHaveBeenCalled())
    expect(seen).not.toHaveBeenCalled()
  })

  it('cerrar la suscripción detiene las reconexiones', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(okStream('event: end\ndata: {}\n\n')))
    const client = new ApiClient('/api/v1', fetchImpl as unknown as typeof fetch)
    const stop = client.watchTower(vi.fn(), vi.fn(), 1)
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalled())
    stop()
    const calls = fetchImpl.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(fetchImpl.mock.calls.length - calls).toBeLessThanOrEqual(1)
  })
})
