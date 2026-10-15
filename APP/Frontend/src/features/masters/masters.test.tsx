import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../../app/App'
import { ApiError } from '../../api/errors'
import type { CsvPreview, Role } from '../../api/types'
import { makeFakeClient, makeParameters } from '../../test/fixtures'

const open = (role: Role = 'tenant_admin', overrides: Record<string, unknown> = {}) => {
  const client = makeFakeClient(role, overrides)
  render(
    <MemoryRouter initialEntries={['/maestros']}>
      <App client={client} />
    </MemoryRouter>,
  )
  return client
}

const tab = (name: string) => screen.getByRole('tab', { name })

afterEach(() => vi.restoreAllMocks())

describe('acceso', () => {
  it('el administrador de empresa ve la opción y la pantalla', async () => {
    open()
    expect(await screen.findByRole('heading', { name: 'Maestros y parámetros' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' })
    expect(within(nav).getByRole('link', { name: 'Maestros y parámetros' })).toBeInTheDocument()
  })

  it.each<Role>(['management', 'dispatcher', 'driver', 'super_admin'])(
    '%s no la ve y abrirla no llama a la API',
    async (role) => {
      const client = open(role)
      expect(await screen.findByText('Permisos insuficientes')).toBeInTheDocument()
      expect(client.masterSchema).not.toHaveBeenCalled()
    },
  )
})

describe('tablas de maestros', () => {
  it('muestra los maestros agrupados y la tabla del primero con unidades y descripción', async () => {
    open()
    expect(await screen.findByRole('table', { name: 'Tipos de vehículo' })).toBeInTheDocument()
    for (const name of ['Tipos de vehículo', 'Corredores', 'Clientes', 'Vehículos', 'Parámetros', 'Historial']) {
      expect(tab(name)).toBeInTheDocument()
    }
    expect(screen.getByText('Descripción de Tipos de vehículo')).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Tipos de vehículo' })
    expect(within(table).getByText('4,5 t')).toBeInTheDocument()
    expect(tab('Tipos de vehículo')).toHaveAttribute('aria-selected', 'true')
  })

  it('cambiar de pestaña carga ese maestro y formatea porcentajes y selecciones', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Corredores' }))
    const table = await screen.findByRole('table', { name: 'Corredores' })
    expect(client.masterRows).toHaveBeenCalledWith('corridor', expect.anything())
    expect(within(table).getByText('85,0 %')).toBeInTheDocument()
    expect(within(table).getByText('turbo')).toBeInTheDocument()
  })

  it('indica cuando solo se muestra una parte de los registros', async () => {
    open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Vehículos' }))
    expect(await screen.findByText(/se muestran los 1 más recientes/)).toBeInTheDocument()
    expect(screen.getByText('Propio')).toBeInTheDocument()
  })

  it('un maestro vacío invita a agregar', async () => {
    open('tenant_admin', {
      masterRows: vi.fn(() => Promise.resolve({ entity: 'x', total: 0, rows: [], truncated: false })),
    })
    expect(await screen.findByText('Sin registros')).toBeInTheDocument()
  })

  it('un error de carga ofrece reintentar', async () => {
    const masterRows = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'ERROR_INTERNO', 'Ocurrió un error interno.'))
      .mockResolvedValue({ entity: 'vehicle_type', total: 0, rows: [], truncated: false })
    open('tenant_admin', { masterRows })
    const alert = await screen.findByRole('alert')
    await userEvent.click(within(alert).getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Sin registros')).toBeInTheDocument()
  })
})

describe('alta, edición y baja', () => {
  it('no deja guardar con campos obligatorios vacíos y no llama a la API', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo' }))
    const dialog = await screen.findByRole('dialog', { name: /Nuevo: Tipo de vehículo/ })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Complete los campos obligatorios')
    expect(within(dialog).getByLabelText(/Nombre/)).toHaveAttribute('aria-invalid', 'true')
    expect(client.masterCreate).not.toHaveBeenCalled()
  })

  it('crea un registro con los valores escritos y refresca la lista', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/Nombre/), 'furgon')
    await userEvent.type(within(dialog).getByLabelText(/Capacidad \(t\)/), '1,5')
    await userEvent.type(within(dialog).getByLabelText(/Pallets/), '3')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(client.masterCreate).toHaveBeenCalledWith('vehicle_type', { name: 'furgon', capacity_t: '1,5', pallets: '3' })
    expect(await screen.findByText('Tipo de vehículo creado.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(client.masterRows).toHaveBeenCalledTimes(2)
  })

  it('muestra el error de validación del servidor sin cerrar el formulario', async () => {
    const masterCreate = vi.fn(() =>
      Promise.reject(new ApiError(422, 'DATO_INVALIDO', 'Capacidad (t) debe ser mayor que 0.')),
    )
    open('tenant_admin', { masterCreate })
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/Nombre/), 'x')
    await userEvent.type(within(dialog).getByLabelText(/Capacidad \(t\)/), '0')
    await userEvent.type(within(dialog).getByLabelText(/Pallets/), '1')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('mayor que 0')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/Nombre/)).toHaveValue('x') // conserva lo escrito
  })

  it('al editar la clave queda bloqueada y se actualiza con la clave original', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Editar turbo' }))
    const dialog = await screen.findByRole('dialog', { name: /Editar: Tipo de vehículo/ })
    expect(within(dialog).getByLabelText(/Nombre/)).toBeDisabled()
    expect(within(dialog).getByText('La clave no se puede cambiar.')).toBeInTheDocument()
    const pallets = within(dialog).getByLabelText(/Pallets/)
    await userEvent.clear(pallets)
    await userEvent.type(pallets, '9')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(client.masterUpdate).toHaveBeenCalledWith(
      'vehicle_type',
      'turbo',
      expect.objectContaining({ name: 'turbo', pallets: '9' }),
    )
    expect(await screen.findByText('Cambios guardados.')).toBeInTheDocument()
  })

  it('las listas de selección salen de otros maestros', async () => {
    open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Corredores' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo' }))
    const select = within(await screen.findByRole('dialog')).getByLabelText(/Tipo de vehículo asignado/)
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Elija una opción…',
      'turbo',
      'sencillo',
    ])
  })

  it('eliminar pide confirmación y cancelar no llama a la API', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar sencillo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Eliminar registro' })
    expect(dialog).toHaveTextContent('queda en el historial con su valor anterior')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    expect(client.masterDelete).not.toHaveBeenCalled()
  })

  it('confirmar elimina y recarga', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar sencillo' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Eliminar' }))
    expect(client.masterDelete).toHaveBeenCalledWith('vehicle_type', 'sencillo')
    expect(await screen.findByText('Registro eliminado.')).toBeInTheDocument()
  })

  it('si otro maestro lo usa muestra el motivo del servidor', async () => {
    const masterDelete = vi.fn(() =>
      Promise.reject(new ApiError(409, 'CONFLICTO', 'No se puede eliminar «turbo»: lo usan 3 registro(s) de corredores.')),
    )
    open('tenant_admin', { masterDelete })
    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar turbo' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('lo usan 3 registro(s)')
  })

  it('los horarios se piden en formato HH:MM con su ayuda', async () => {
    open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Clientes' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/Ventana desde/)).toHaveAttribute('placeholder', 'HH:MM')
    expect(within(dialog).getByText('Formato HH:MM')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/Dirección/)).not.toHaveAttribute('aria-invalid')
  })
})

describe('exportar', () => {
  it('Excel y CSV se piden al servidor y se guardan con el nombre recibido', async () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const client = open()
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar Excel' }))
    expect(client.download).toHaveBeenCalledWith('/masters/entities/vehicle_type/export?format=xlsx')
    await userEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }))
    expect(client.download).toHaveBeenLastCalledWith('/masters/entities/vehicle_type/export?format=csv')
    expect(click).toHaveBeenCalledTimes(2)
  })

  it('si falla la exportación lo dice', async () => {
    const download = vi.fn(() => Promise.reject(new ApiError(403, 'PERMISO_DENEGADO', 'No tiene permiso.')))
    open('tenant_admin', { download })
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar Excel' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No tiene permiso.')
  })
})

describe('carga CSV', () => {
  const preview = (patch: Partial<CsvPreview> = {}): CsvPreview => ({
    entity: 'customer',
    rows_total: 2,
    rows_valid: 2,
    to_create: 1,
    to_update: 1,
    errors: [],
    errors_truncated: false,
    sample: [],
    can_apply: true,
    ...patch,
  })

  const openDialog = async (overrides: Record<string, unknown>) => {
    const client = open('tenant_admin', overrides)
    await userEvent.click(await screen.findByRole('tab', { name: 'Clientes' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Cargar CSV' }))
    return { client, dialog: await screen.findByRole('dialog', { name: /Cargar CSV: Clientes/ }) }
  }

  it('lista las columnas esperadas y no deja aplicar sin previsualizar', async () => {
    const { dialog } = await openDialog({})
    expect(dialog).toHaveTextContent('code, name, address (opcional)')
    expect(within(dialog).getByRole('button', { name: 'Aplicar carga' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Previsualizar' })).toBeDisabled()
  })

  it('previsualiza un archivo, muestra el resumen y permite aplicar', async () => {
    const csvPreview = vi.fn(() => Promise.resolve(preview()))
    const csvApply = vi.fn(() => Promise.resolve({ created: 1, updated: 1 }))
    const { dialog } = await openDialog({ csvPreview, csvApply })
    const file = new File(['code,name\nC-1,Uno'], 'clientes.csv', { type: 'text/csv' })
    await userEvent.upload(within(dialog).getByLabelText('Archivo CSV'), file)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Previsualizar' }))
    expect(csvPreview).toHaveBeenCalledWith('customer', 'code,name\nC-1,Uno')
    const result = await within(dialog).findByRole('region', { name: 'Resultado de la previsualización' })
    expect(result).toHaveTextContent('Lista para aplicar')
    expect(result).toHaveTextContent('2 filas · 2 válidas · 1 nuevas · 1 actualizaciones')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Aplicar carga' }))
    expect(csvApply).toHaveBeenCalledWith('customer', 'code,name\nC-1,Uno')
    expect(await screen.findByText('Carga aplicada: 1 creados y 1 actualizados.')).toBeInTheDocument()
  })

  it('con errores muestra fila, columna y qué corregir, y bloquea la carga', async () => {
    const csvPreview = vi.fn(() =>
      Promise.resolve(
        preview({
          rows_valid: 0,
          can_apply: false,
          errors: [
            { row: 2, column: 'window_end', message: 'La ventana 14:00–10:00 no es válida: la hora final debe ser posterior a la inicial.' },
            { row: 3, column: 'lat', message: 'Latitud no puede ser mayor que 13,5.' },
          ],
        }),
      ),
    )
    const { dialog } = await openDialog({ csvPreview })
    await userEvent.type(within(dialog).getByLabelText('…o pegue el contenido'), 'code\nC-1')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Previsualizar' }))
    const table = await within(dialog).findByRole('table', { name: 'Errores del archivo' })
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(table).toHaveTextContent('14:00–10:00')
    expect(within(dialog).getByText('Tiene errores: no se puede aplicar')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Aplicar carga' })).toBeDisabled()
  })

  it('editar el contenido invalida la previsualización anterior', async () => {
    const { dialog } = await openDialog({ csvPreview: vi.fn(() => Promise.resolve(preview())) })
    const text = within(dialog).getByLabelText('…o pegue el contenido')
    await userEvent.type(text, 'a')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Previsualizar' }))
    await within(dialog).findByRole('region', { name: 'Resultado de la previsualización' })
    await userEvent.type(text, 'b')
    expect(within(dialog).queryByRole('region', { name: 'Resultado de la previsualización' })).toBeNull()
    expect(within(dialog).getByRole('button', { name: 'Aplicar carga' })).toBeDisabled()
  })

  it('un archivo demasiado grande se rechaza antes de enviarlo', async () => {
    const { client, dialog } = await openDialog({})
    const big = new File(['x'.repeat(200_001)], 'grande.csv', { type: 'text/csv' })
    await userEvent.upload(within(dialog).getByLabelText('Archivo CSV'), big)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('supera el tamaño permitido')
    expect(client.csvPreview).not.toHaveBeenCalled()
  })

  it('muestra el error del servidor al procesar', async () => {
    const csvPreview = vi.fn(() => Promise.reject(new ApiError(422, 'DATO_INVALIDO', 'El archivo está vacío.')))
    const { dialog } = await openDialog({ csvPreview })
    await userEvent.type(within(dialog).getByLabelText('…o pegue el contenido'), ' ')
    await userEvent.type(within(dialog).getByLabelText('…o pegue el contenido'), 'x')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Previsualizar' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('El archivo está vacío.')
  })
})

describe('parámetros', () => {
  const goToParameters = async (overrides: Record<string, unknown> = {}) => {
    const client = open('tenant_admin', overrides)
    await userEvent.click(await screen.findByRole('tab', { name: 'Parámetros' }))
    await screen.findByRole('table', { name: 'Parámetros de Capacidad de flota' })
    return client
  }

  it('agrupa por área, muestra el valor vigente con su unidad y sus versiones', async () => {
    await goToParameters()
    const cap = screen.getByRole('table', { name: 'Parámetros de Capacidad de flota' })
    expect(within(cap).getByRole('row', { name: /Reserva de flota/ })).toHaveTextContent('8,0 %')
    expect(within(cap).getAllByText('Valor inicial').length).toBeGreaterThan(0)
    const routing = screen.getByRole('table', { name: 'Parámetros de Ruteo diario' })
    expect(within(routing).getByRole('row', { name: /Hora de salida/ })).toHaveTextContent('06:00')
    expect(screen.getByText(/aplican en la siguiente consulta del tablero/)).toBeInTheDocument()
  })

  it('cambiar un valor con vigencia y motivo llama al backend y avisa', async () => {
    const client = await goToParameters()
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar Reserva de flota' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cambiar: Reserva de flota' })
    expect(dialog).toHaveTextContent('Reserva de flota sobre la requerida.')
    const value = within(dialog).getByLabelText(/Nuevo valor/)
    await userEvent.clear(value)
    await userEvent.type(value, '12')
    await userEvent.type(within(dialog).getByLabelText(/Vigente desde/), '2999-01-01')
    await userEvent.type(within(dialog).getByLabelText(/Motivo/), 'Temporada alta')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(client.setParameter).toHaveBeenCalledWith('reserve', '12', '2999-01-01', 'Temporada alta')
    expect(await screen.findByText('Parámetro programado: aplicará desde el 2999-01-01.')).toBeInTheDocument()
  })

  it('sin fecha se aplica desde hoy y recuerda que el valor anterior queda en el historial', async () => {
    const client = await goToParameters()
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar Reserva de flota' }))
    const dialog = await screen.findByRole('dialog')
    const value = within(dialog).getByLabelText(/Nuevo valor/)
    await userEvent.clear(value)
    await userEvent.type(value, '10')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(client.setParameter).toHaveBeenCalledWith('reserve', '10', undefined, undefined)
    expect(await screen.findByText(/valor anterior queda en el historial/)).toBeInTheDocument()
  })

  it('no envía un valor vacío y muestra el error del servidor', async () => {
    const setParameter = vi.fn(() =>
      Promise.reject(new ApiError(422, 'DATO_INVALIDO', 'Reserva de flota no puede ser mayor que 50.')),
    )
    const client = await goToParameters({ setParameter })
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar Reserva de flota' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.clear(within(dialog).getByLabelText(/Nuevo valor/))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Escriba el nuevo valor.')
    expect(client.setParameter).not.toHaveBeenCalled()
    await userEvent.type(within(dialog).getByLabelText(/Nuevo valor/), '99')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('no puede ser mayor que 50')
  })

  it('marca las versiones programadas', async () => {
    const [first, ...rest] = makeParameters()
    const scheduled = {
      ...first!,
      versions: [
        { value: 12, valid_from: '2999-01-01', set_by: 'admin', set_at: 'x', note: 'Temporada alta', in_force: false, scheduled: true },
        ...first!.versions,
      ],
    }
    await goToParameters({ masterParameters: vi.fn(() => Promise.resolve([scheduled, ...rest])) })
    await userEvent.click(screen.getAllByText('2 versión(es)')[0]!)
    expect(screen.getByText('Programada')).toBeInTheDocument()
    expect(screen.getAllByText('Vigente').length).toBeGreaterThan(0)
  })
})

describe('historial', () => {
  it('muestra quién, cuándo, qué y el valor anterior', async () => {
    open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Historial' }))
    const table = await screen.findByRole('table', { name: /Historial de cambios/ })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    const update = within(table).getByRole('row', { name: /Modificó · Tipo de vehículo turbo/ })
    expect(update).toHaveTextContent('pallets: 8 → 9')
    const param = within(table).getByRole('row', { name: /Cambió el parámetro · Parámetro reserve/ })
    expect(param).toHaveTextContent('value: 8 → 12')
    expect(param).toHaveTextContent('2026-11-01')
    expect(param).toHaveTextContent('Temporada alta')
    expect(within(table).getByText('Registro nuevo')).toBeInTheDocument()
  })

  it('filtra por maestro', async () => {
    const client = open()
    await userEvent.click(await screen.findByRole('tab', { name: 'Historial' }))
    await screen.findByRole('table', { name: /Historial de cambios/ })
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por'), 'Clientes')
    await screen.findByRole('table', { name: /Historial de cambios/ })
    expect(client.masterHistory).toHaveBeenLastCalledWith('customer', expect.anything())
  })

  it('sin cambios invita a hacerlos', async () => {
    open('tenant_admin', { masterHistory: vi.fn(() => Promise.resolve([])) })
    await userEvent.click(await screen.findByRole('tab', { name: 'Historial' }))
    expect(await screen.findByText('Sin cambios registrados')).toBeInTheDocument()
  })
})

describe('exportaciones Excel de otras pantallas', () => {
  const route = async (role: Role, path: string) => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const client = makeFakeClient(role)
    render(
      <MemoryRouter initialEntries={[path]}>
        <App client={client} />
      </MemoryRouter>,
    )
    return client
  }

  it('capacidad descarga el Excel del servidor', async () => {
    const client = await route('management', '/capacidad')
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar Excel' }))
    expect(client.download).toHaveBeenCalledWith('/capacity/export.xlsx')
  })

  it('la hoja del conductor descarga su Excel', async () => {
    const client = await route('driver', '/mi-ruta')
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar Excel' }))
    expect(client.download).toHaveBeenCalledWith('/routing/driver/route/export?format=xlsx')
  })
})
