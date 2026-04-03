import { Component } from 'react'

/**
 * React Error Boundary — catches rendering crashes and shows
 * a recovery UI instead of a white screen.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Caught:', error, info?.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: '#020917', color: '#eef4ff',
        fontFamily: "'Sora', sans-serif",
      }}>
        <div style={{
          maxWidth: 480, padding: 40, textAlign: 'center',
          background: 'rgba(5,12,30,.72)', borderRadius: 16,
          border: '1px solid rgba(255,255,255,.07)',
          backdropFilter: 'blur(20px)',
          boxShadow: '0 4px 24px rgba(0,0,0,.25)',
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>
            Something went wrong
          </h2>
          <p style={{ fontSize: 14, color: '#94a3b8', marginBottom: 20, lineHeight: 1.6 }}>
            An unexpected error occurred. This is usually temporary.
          </p>
          <details style={{
            fontSize: 12, color: '#4b5e7a', marginBottom: 20, textAlign: 'left',
            background: 'rgba(255,255,255,.03)', borderRadius: 8, padding: 12,
            border: '1px solid rgba(255,255,255,.07)',
          }}>
            <summary style={{ cursor: 'pointer', marginBottom: 8 }}>
              Error details
            </summary>
            <pre style={{
              whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              fontFamily: "'Space Mono', monospace", fontSize: 11,
            }}>
              {this.state.error?.toString()}
            </pre>
          </details>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              window.location.href = '/'
            }}
            style={{
              background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
              color: '#fff', border: '1px solid rgba(37,99,235,.5)',
              borderRadius: 10, padding: '10px 24px', fontSize: 14,
              fontWeight: 600, cursor: 'pointer',
              fontFamily: "'Sora', sans-serif",
              boxShadow: '0 4px 18px rgba(37,99,235,.4)',
            }}
          >
            ↻ Reload App
          </button>
        </div>
      </div>
    )
  }
}
