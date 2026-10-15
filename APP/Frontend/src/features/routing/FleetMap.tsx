import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'

import type { RoutingSnapshot } from '../../api/types'
import {
  STOP_KIND_LABELS,
  colorOfVehicle,
  formatClock,
  vehicleStatusLabel,
  windowText,
} from '../../domain-ui/routing'

// Teselas públicas de OpenStreetMap: sin API key ni servicios de pago. La política de uso de OSM
// exige atribución visible y uso moderado; para producción se usaría un proveedor de teselas propio.
const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

const escapeHtml = (text: string): string =>
  text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

/**
 * Mapa de la flota. El mapa es un apoyo visual: toda la información también está en las tablas
 * de la pantalla. Los trayectos se dibujan en línea recta entre paradas (DEMO-ONLY).
 */
export function FleetMap({ snapshot }: { snapshot: RoutingSnapshot }) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const fitted = useRef(false)

  useEffect(() => {
    if (!container.current || map.current) return
    const created = L.map(container.current, { zoomControl: true }).setView(
      [snapshot.depot.lat, snapshot.depot.lon],
      11,
    )
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(created)
    layer.current = L.layerGroup().addTo(created)
    map.current = created
    return () => {
      created.remove()
      map.current = null
      layer.current = null
      fitted.current = false
    }
    // El mapa se crea una sola vez; los datos se repintan en el efecto siguiente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const group = layer.current
    const current = map.current
    if (!group || !current) return
    group.clearLayers()
    const points: L.LatLngTuple[] = [[snapshot.depot.lat, snapshot.depot.lon]]

    L.marker([snapshot.depot.lat, snapshot.depot.lon], {
      icon: L.divIcon({
        className: 'map-pin map-pin-depot',
        html: '<span>CEDI</span>',
        iconSize: [46, 22],
      }),
      title: snapshot.depot.name,
    }).addTo(group)

    const vehicles = snapshot.vehicles
    for (const vehicle of vehicles) {
      if (vehicle.route_status === 'standby') continue
      const color = colorOfVehicle(vehicles, vehicle.id)
      const stops = snapshot.stops
        .filter((s) => s.vehicle_id === vehicle.id)
        .sort((a, b) => a.sequence - b.sequence)
      const line = stops.map((s) => [s.lat, s.lon] as L.LatLngTuple)
      if (line.length > 1) {
        L.polyline(line, { color, weight: 3, opacity: 0.55 }).addTo(group)
      }
      for (const stop of stops) {
        points.push([stop.lat, stop.lon])
        const fill = stop.state === 'completed' ? '#9aa3af' : stop.at_risk ? '#dc2626' : color
        const marker = L.circleMarker([stop.lat, stop.lon], {
          radius: stop.state === 'in_service' ? 9 : 6,
          color: stop.at_risk ? '#7f1d1d' : '#ffffff',
          weight: 2,
          fillColor: fill,
          fillOpacity: stop.state === 'completed' ? 0.55 : 0.95,
        })
        const late = stop.delay_min > 0 ? ` · retraso ${Math.round(stop.delay_min)} min` : ''
        marker
          .bindTooltip(
            `<strong>${escapeHtml(stop.label)}</strong><br>` +
              `${STOP_KIND_LABELS[stop.kind]} · ${escapeHtml(stop.plate)} · #${stop.sequence}<br>` +
              `Llegada ${formatClock(stop.arrival_min)} · ventana ${windowText(stop)}${late}`,
          )
          .addTo(group)
      }
      const here: L.LatLngTuple = [vehicle.lat, vehicle.lon]
      points.push(here)
      const next = stops.find((s) => s.state === 'pending')
      if (next && vehicle.status !== 'broken') {
        L.polyline([here, [next.lat, next.lon]], {
          color,
          weight: 2,
          dashArray: '4 6',
          opacity: 0.9,
        }).addTo(group)
      }
      const broken = vehicle.status === 'broken'
      const stale = vehicle.gps_status === 'no_signal'
      L.marker(here, {
        icon: L.divIcon({
          className: `map-pin map-pin-vehicle${broken ? ' map-pin-broken' : ''}${stale ? ' map-pin-stale' : ''}`,
          html: `<span style="border-color:${color}">${broken ? '✖ ' : stale ? '⚠ ' : ''}${escapeHtml(vehicle.plate)}</span>`,
          iconSize: [78, 24],
        }),
        title: `${vehicle.plate}: ${vehicleStatusLabel(vehicle.status)}${
          stale ? ` · sin señal GPS (última posición hace ${Math.round(vehicle.gps_age_min ?? 0)} min)` : ''
        }`,
        zIndexOffset: 1000,
      }).addTo(group)
    }

    if (!fitted.current && points.length > 1) {
      current.fitBounds(L.latLngBounds(points), { padding: [30, 30] })
      fitted.current = true
    }
  }, [snapshot])

  return (
    <div
      ref={container}
      className="fleet-map"
      role="region"
      aria-label="Mapa de la flota (apoyo visual; los mismos datos están en las tablas)"
      data-testid="fleet-map"
    />
  )
}
