interface Toast {
  id: string
  tone: 'info' | 'success' | 'warn' | 'error'
  message: string
}

interface ToastStackProps {
  toasts: Toast[]
}

export function ToastStack({ toasts }: ToastStackProps) {
  if (toasts.length === 0) {
    return null
  }

  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-card ${toast.tone}`}>
          {toast.message}
        </div>
      ))}
    </div>
  )
}
