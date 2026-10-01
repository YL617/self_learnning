import { beforeEach, describe, expect, it } from 'vitest'

import router from './index'

function loginAs(user: Record<string, unknown> | null) {
  localStorage.setItem('ai_study_token', 'test-token')
  if (user) localStorage.setItem('ai_study_user', JSON.stringify(user))
}

async function go(path: string) {
  await router.push(path).catch(() => undefined)
  await router.isReady()
  return router.currentRoute.value
}

describe('router 后台访问控制', () => {
  beforeEach(async () => {
    localStorage.clear()
    await router.replace('/login').catch(() => undefined)
    await router.isReady()
  })

  it('未登录时重定向到登录页', async () => {
    const route = await go('/admin/knowledge-points')
    expect(route.name).toBe('login')
  })

  it('普通用户无法进入知识点管理页', async () => {
    loginAs({ id: 1, username: 'student', role: 'user' })
    const route = await go('/admin/knowledge-points')
    expect(route.name).toBe('dashboard')
  })

  it('管理员可以进入知识点管理页', async () => {
    loginAs({ id: 1, username: 'root', role: 'admin' })
    const route = await go('/admin/knowledge-points')
    expect(route.name).toBe('admin-knowledge-points')
    expect(route.path).toBe('/admin/knowledge-points')
  })

  it('is_admin 标记同样视为管理员', async () => {
    loginAs({ id: 2, username: 'ops', is_admin: true })
    const route = await go('/admin/knowledge-points')
    expect(route.name).toBe('admin-knowledge-points')
  })

  it('知识点管理页已注册在后台布局下', () => {
    const record = router.getRoutes().find((item) => item.name === 'admin-knowledge-points')
    expect(record?.path).toBe('/admin/knowledge-points')
    expect(record?.components?.default).toBeTruthy()
  })
})
