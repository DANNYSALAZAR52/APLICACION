import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { ApiClient } from './api/client'
import { App } from './app/App'
import './styles/app.css'

const client = new ApiClient()
const container = document.getElementById('root')
if (!container) throw new Error('No se encontró el contenedor #root')

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App client={client} />
    </BrowserRouter>
  </StrictMode>,
)
