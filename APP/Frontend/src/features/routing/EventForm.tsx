import { useState } from 'react'
import type { FormEvent } from 'react'

import type { EventRequest, RoutingSnapshot } from '../../api/types'
import { EVENT_LABELS, formatClock, parseClock } from '../../domain-ui/routing'
import { useRouting } from './RoutingProvider'

type FormType = 'road_closure' | 'urgent_order' | 'window_change' | 'breakdown'
const TYPES: FormType[] = ['road_closure', 'urgent_order', 'window_change', 'breakdown']

interface Props {
  snapshot: RoutingSnapshot
}

const numberOr = (text: string): number => Number(text.replace(',', '.'))

/** Formulario de "Inyectar evento": valida lo evidente; el backend vuelve a validar todo. */
export function EventForm({ snapshot }: Props) {
  const { injectEvent, busy } = useRouting()
  const [type, setType] = useState<FormType>('road_closure')
  const [errors, setErrors] = useState<string[]>([])

  const [label, setLabel] = useState('Calle 80')
  const [lat, setLat] = useState('4.722')
  const [lon, setLon] = useState('-74.100')
  const [radius, setRadius] = useState('2.5')
  const [factor, setFactor] = useState('2.5')
  const [duration, setDuration] = useState('255')

  const [customer, setCustomer] = useState(snapshot.customers[0]?.[0] ?? '')
  const [kg, setKg] = useState('300')
  const [m3, setM3] = useState('1')

  const now = snapshot.clock.minute
  const [winStart, setWinStart] = useState(formatClock(now + 30))
  const [winEnd, setWinEnd] = useState(formatClock(Math.min(now + 6 * 60, 23 * 60 + 59)))
  const [order, setOrder] = useState(snapshot.pending_orders[0]?.[0] ?? '')
  const [vehicle, setVehicle] = useState('')

  const breakable = snapshot.vehicles.filter(
    (v) => v.route_status === 'active' && v.pending_stops > 0 && v.status !== 'broken',
  )

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const found: string[] = []
    let body: EventRequest | null = null
    const start = parseClock(winStart)
    const end = parseClock(winEnd)
    const needWindow = type === 'urgent_order' || type === 'window_change'
    if (needWindow) {
      if (start === null || end === null) found.push('Escriba las horas de la ventana como HH:MM.')
      else if (end <= start) {
        found.push(
          `La ventana ${winStart}–${winEnd} no es válida: la hora final debe ser posterior a la inicial.`,
        )
      }
    }
    if (type === 'road_closure') {
      const values = [numberOr(lat), numberOr(lon), numberOr(radius), numberOr(factor), numberOr(duration)]
      if (!label.trim()) found.push('Indique el nombre del cierre (por ejemplo, la calle).')
      if (values.some((v) => Number.isNaN(v))) found.push('Latitud, longitud, radio, factor y duración deben ser números.')
      else {
        if (values[2]! <= 0) found.push('El radio debe ser mayor que cero.')
        if (values[3]! < 1) found.push('El factor debe ser 1 o mayor (1 = sin efecto).')
        if (values[4]! <= 0) found.push('La duración debe ser mayor que cero.')
        body = {
          type,
          label: label.trim(),
          lat: values[0]!,
          lon: values[1]!,
          radius_km: values[2]!,
          factor: values[3]!,
          duration_min: values[4]!,
        }
      }
    } else if (type === 'urgent_order') {
      if (!customer) found.push('Elija el cliente del pedido urgente.')
      if (!(numberOr(kg) > 0)) found.push('Los kg deben ser mayores que cero.')
      if (Number.isNaN(numberOr(m3)) || numberOr(m3) < 0) found.push('Los m³ no pueden ser negativos.')
      body = {
        type,
        customer_code: customer,
        kg: numberOr(kg),
        m3: numberOr(m3),
        window_start: winStart.trim(),
        window_end: winEnd.trim(),
      }
    } else if (type === 'window_change') {
      if (!order) found.push('No hay pedidos pendientes para cambiar de ventana.')
      body = { type, order_id: order, window_start: winStart.trim(), window_end: winEnd.trim() }
    } else {
      if (!vehicle) found.push('Elija el vehículo averiado.')
      body = { type, vehicle_id: vehicle }
    }
    setErrors(found)
    if (found.length > 0 || body === null) return
    await injectEvent(body)
  }

  return (
    <form className="event-form" onSubmit={(e) => void submit(e)} noValidate aria-label="Inyectar evento">
      <fieldset>
        <legend>Tipo de evento</legend>
        <div className="radio-row">
          {TYPES.map((t) => (
            <label key={t} className="radio">
              <input
                type="radio"
                name="event-type"
                value={t}
                checked={type === t}
                onChange={() => {
                  setType(t)
                  setErrors([])
                }}
              />{' '}
              {EVENT_LABELS[t]}
            </label>
          ))}
        </div>
      </fieldset>

      {errors.length > 0 ? (
        <div className="alert alert-error" role="alert">
          <ul className="plain">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {type === 'road_closure' ? (
        <div className="form-grid">
          <div className="field">
            <label htmlFor="ev-label">Calle o zona</label>
            <input id="ev-label" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
          </div>
          <div className="field">
            <label htmlFor="ev-lat">Latitud del centro</label>
            <input id="ev-lat" value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="ev-lon">Longitud del centro</label>
            <input id="ev-lon" value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="ev-radius">Radio (km)</label>
            <input id="ev-radius" value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="ev-factor">Factor de tiempo (×)</label>
            <input id="ev-factor" value={factor} onChange={(e) => setFactor(e.target.value)} inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="ev-duration">Duración (min)</label>
            <input id="ev-duration" value={duration} onChange={(e) => setDuration(e.target.value)} inputMode="numeric" />
          </div>
        </div>
      ) : null}

      {type === 'urgent_order' ? (
        <div className="form-grid">
          <div className="field">
            <label htmlFor="ev-customer">Cliente</label>
            <select id="ev-customer" value={customer} onChange={(e) => setCustomer(e.target.value)}>
              {snapshot.customers.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ev-kg">Peso (kg)</label>
            <input id="ev-kg" value={kg} onChange={(e) => setKg(e.target.value)} inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="ev-m3">Volumen (m³)</label>
            <input id="ev-m3" value={m3} onChange={(e) => setM3(e.target.value)} inputMode="decimal" />
          </div>
          <WindowFields start={winStart} end={winEnd} onStart={setWinStart} onEnd={setWinEnd} />
        </div>
      ) : null}

      {type === 'window_change' ? (
        <div className="form-grid">
          <div className="field">
            <label htmlFor="ev-order">Pedido pendiente</label>
            <select id="ev-order" value={order} onChange={(e) => setOrder(e.target.value)}>
              {snapshot.pending_orders.map(([id, name]) => (
                <option key={id} value={id}>
                  {id} · {name}
                </option>
              ))}
            </select>
          </div>
          <WindowFields start={winStart} end={winEnd} onStart={setWinStart} onEnd={setWinEnd} />
        </div>
      ) : null}

      {type === 'breakdown' ? (
        <div className="form-grid">
          <div className="field">
            <label htmlFor="ev-vehicle">Vehículo averiado</label>
            <select id="ev-vehicle" value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
              <option value="">Elija un vehículo…</option>
              {breakable.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.plate} · {v.pending_stops} entregas pendientes
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : null}

      <p className="muted small">
        El sistema solo <strong>propone</strong>: nada cambia hasta que usted apruebe la propuesta.
      </p>
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? 'Calculando propuesta…' : 'Inyectar evento'}
      </button>
    </form>
  )
}

function WindowFields(props: {
  start: string
  end: string
  onStart: (v: string) => void
  onEnd: (v: string) => void
}) {
  return (
    <>
      <div className="field">
        <label htmlFor="ev-win-start">Ventana desde (HH:MM)</label>
        <input id="ev-win-start" value={props.start} onChange={(e) => props.onStart(e.target.value)} placeholder="09:00" />
      </div>
      <div className="field">
        <label htmlFor="ev-win-end">Ventana hasta (HH:MM)</label>
        <input id="ev-win-end" value={props.end} onChange={(e) => props.onEnd(e.target.value)} placeholder="13:00" />
      </div>
    </>
  )
}
