import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ToastProvider }       from './context/ToastContext'
import { SocketProvider }      from './context/SocketContext'
import { EnrollQueueProvider } from './context/EnrollQueueContext'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <SocketProvider>
          <ToastProvider>
            <EnrollQueueProvider>
              <App />
            </EnrollQueueProvider>
          </ToastProvider>
        </SocketProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>
)
