import React, { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Dashboard Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          padding: '20px',
          fontFamily: 'system-ui, sans-serif',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ margin: '0 0 8px', color: '#1F2937' }}>Something went wrong</h2>
          <p style={{ margin: '0 0 16px', color: '#6B7280', maxWidth: 400 }}>
            The dashboard encountered an error. Check the console for details.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              background: '#4F46E5',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
