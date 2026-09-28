import type { ObjectDirective } from 'vue'

type Field = HTMLInputElement | HTMLTextAreaElement
const checks = new WeakMap<Field, () => void>()
export const codepoints: ObjectDirective<Field, number> = {
  mounted(element, binding) {
    const minimum = Math.max(0, element.minLength)
    element.removeAttribute('minlength')
    element.removeAttribute('maxlength')
    const check = () => {
      const length = Array.from(element.value).length
      element.setCustomValidity(length > binding.value ? `最多允许 ${binding.value} 个字符` :
        length > 0 && length < minimum ? `至少需要 ${minimum} 个字符` : '')
    }
    checks.set(element, check)
    element.addEventListener('input', check)
    check()
  },
  updated(element) { checks.get(element)?.() },
  unmounted(element) { const check = checks.get(element); if (check) element.removeEventListener('input', check) },
}
