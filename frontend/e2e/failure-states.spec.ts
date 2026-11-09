import { test, expect } from '@playwright/test'

test('retry tracks only the new task through a dropped connection and failed validation', async ({ page }) => {
  const failed = { id: 'old', course_id: 'data_structure', topic: '顺序栈的应用', resource_type: 'lecture', status: 'failed', error_code: 'TASK_TIMEOUT', resource_id: null, content_regenerations: 0, created_at: '2026-01-01T00:00:00Z' }
  const accepted = { ...failed, id: 'new', status: 'queued', error_code: null }
  await page.route('**/api/auth/session', route => route.fulfill({ json: { user: { id: 'fixture', username: 'learner' }, csrf_token: 'fixture' } }))
  await page.route('**/api/tasks', route => route.fulfill({ json: [failed] }))
  await page.route('**/api/courses', route => route.fulfill({ json: [] }))
  await page.route('**/api/model-settings', route => route.fulfill({ json: { version: 0, configured: false } }))
  await page.route('**/api/tasks/old/retry', route => route.fulfill({ status: 202, json: accepted }))
  let reads = 0
  await page.route('**/api/tasks/new', route => {
    reads++
    if (reads === 1) return route.abort('internetdisconnected')
    if (reads === 2) return route.fulfill({ json: { ...accepted, status: 'generating', content_regenerations: 1 } })
    return route.fulfill({ json: { ...failed, id: 'new', error_code: 'CONTENT_REJECTED', content_regenerations: 1 } })
  })
  await page.goto('/')
  await page.getByText('最近生成记录', { exact: true }).click()
  await page.getByRole('button', { name: '沿用原配置重试' }).click()
  const progress = page.getByRole('region', { name: '生成过程' })
  await expect(progress.getByText(/进度连接暂时中断/)).toBeVisible()
  await expect(progress.locator('[aria-current="step"]')).toContainText('生成学习资源')
  await expect(progress.getByText('已根据核验结果重新生成 1 次。')).toBeVisible()
  await expect(progress.getByRole('alert')).toContainText('CONTENT_REJECTED')
  await expect(progress.getByRole('button', { name: '沿用原配置重试' })).toBeEnabled()
  await expect(page).toHaveURL(/\/$/)
})

test('loading, empty, failure, disconnected logout and expired session states', async ({ page }, testInfo) => {
  const username = `err_${testInfo.project.name}_${Date.now().toString().slice(-7)}`
  let releaseCourses!: () => void
  const courseGate = new Promise<void>(resolve => { releaseCourses = resolve })
  await page.route('**/api/courses', async route => { await courseGate; await route.continue() })
  await page.goto('/login')
  await page.getByRole('button', { name: '还没有账号？创建账号' }).click()
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill('Study2026')
  await page.getByLabel('确认密码').fill('Study2026')
  await page.getByRole('button', { name: '注册并进入' }).click()
  try {
    await expect(page.getByRole('status').filter({ hasText: '正在加载学习空间…' })).toBeVisible()
  } finally { releaseCourses() }
  await expect(page.getByText('正在加载学习空间…')).toHaveCount(0)
  await expect(page.getByText('等待开始', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '开始生成' })).toBeDisabled()

  await page.route('**/api/auth/logout', route => route.abort('internetdisconnected'))
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('服务端退出尚未确认')
  await expect(page.getByRole('navigation')).toBeVisible()
  await page.unroute('**/api/auth/logout')

  await page.route('**/api/resources**', route => route.fulfill({
    status: 503, json: { error: { code: 'DATABASE_UNAVAILABLE', message: '数据服务暂时不可用' } },
  }))
  await page.getByRole('link', { name: '学习历史', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('数据服务暂时不可用')
  await page.unroute('**/api/resources**')
  await page.reload()
  await expect(page.getByText(/还没有|暂无|没有符合/).first()).toBeVisible()

  // Frontend handling of a server 401; database expiry is covered by API integration tests.
  await page.route('**/api/resources**', route => route.fulfill({
    status: 401, json: { error: { code: 'AUTH_REQUIRED', message: '请先登录' } },
  }))
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible()
})
