import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource/caveat/500.css'
import '@fontsource/caveat/700.css'
import '@fontsource/patrick-hand/400.css'
import '@fontsource/courier-prime/400.css'
import '@fontsource/courier-prime/700.css'
import './index.css'
import { App } from './App'
import { AppProvider } from './state/app'
import { PanelProvider } from './state/panels'

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: true, staleTime: 5_000, retry: 1 } } })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AppProvider>
          <PanelProvider>
            <App />
          </PanelProvider>
        </AppProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
