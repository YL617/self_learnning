import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import router from '@/router'
import AdminLayout from './AdminLayout.vue'

async function setup() {
  const wrapper = mount(AdminLayout, {
    global: {
      plugins: [router],
      // 只关心侧边导航，路由视图里的页面有各自的 spec（且需要 Pinia 等依赖）。
      stubs: { RouterView: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('AdminLayout 导航', () => {
  beforeEach(async () => {
    localStorage.clear()
    await router.replace('/login').catch(() => undefined)
    await router.isReady()
  })

  it('导航里包含「知识库导入」入口，指向 /admin/knowledge-import', async () => {
    const wrapper = await setup()
    const item = wrapper
      .findAll('.admin-nav-item')
      .find((el: any) => el.text() === '知识库导入')

    expect(item).toBeTruthy()
    expect(item!.attributes('href')).toBe('/admin/knowledge-import')
  })

  it('知识库导入排在知识点管理之后、文档管理之前，保持信息架构连续', async () => {
    const wrapper = await setup()
    const labels = wrapper.findAll('.admin-nav-item').map((el: any) => el.text())
    expect(labels.indexOf('知识库导入')).toBe(labels.indexOf('知识点管理') + 1)
    expect(labels.indexOf('知识库导入')).toBe(labels.indexOf('文档管理') - 1)
  })
})
