const TOAST_EVENT = 'xspend:toast'

export function showToast(message, type = 'success') {
  if (typeof window === 'undefined' || !message) return
  window.dispatchEvent(
    new CustomEvent(TOAST_EVENT, {
      detail: {
        id: Date.now() + Math.random(),
        message: String(message),
        type,
      },
    })
  )
}

export function subscribeToast(handler) {
  const listener = (event) => handler(event.detail)
  window.addEventListener(TOAST_EVENT, listener)
  return () => window.removeEventListener(TOAST_EVENT, listener)
}
