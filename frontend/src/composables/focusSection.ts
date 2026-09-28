import { nextTick } from 'vue'

/** Keep keyboard focus and visual position together without animating reduced-motion users. */
export async function focusSection(element: () => HTMLElement | null) {
  await nextTick()
  const target = element()
  if (!target) return
  target.focus({ preventScroll: true })
  target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}
