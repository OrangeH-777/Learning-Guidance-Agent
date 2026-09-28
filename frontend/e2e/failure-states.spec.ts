import { test, expect } from '@playwright/test'

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
    await expect(page.getByRole('status')).toHaveText('正在加载学习空间…')
  } finally { releaseCourses() }
  await expect(page.getByText('正在加载学习空间…')).toHaveCount(0)
  await expect(page.getByText(/还没有生成任务/)).toBeVisible()
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
