import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Metric } from 'web-vitals'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

function reportWebVital(metric: Metric) {
  const value =
    metric.name === 'CLS'
      ? metric.value.toFixed(3)
      : `${Math.round(metric.value)} ms`

  console.info(
    `[Web Vitals] ${metric.name}: ${value} (${metric.rating})`,
    metric,
  )
}

void import('web-vitals').then(({ onCLS, onFCP, onINP, onLCP, onTTFB }) => {
  onCLS(reportWebVital)
  onFCP(reportWebVital)
  onINP(reportWebVital)
  onLCP(reportWebVital)
  onTTFB(reportWebVital)
})
