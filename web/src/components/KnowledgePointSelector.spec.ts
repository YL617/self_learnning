import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import type { KnowledgePoint } from '@/types'
import KnowledgePointSelector from './KnowledgePointSelector.vue'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: { list: vi.fn() },
  toKnowledgePointNameMap: (items: { id: number; name: string }[]) =>
    Object.fromEntries(items.map((item) => [item.id, item.name])),
}))

function kp(id: number, name: string, subject = '数据结构'): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject,
    parent_id: null,
    description: null,
    status: 'active',
    source: 'admin',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
  }
}

describe('KnowledgePointSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按 subject 加载并渲染选项', async () => {
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({
      data: [kp(1, '栈'), kp(2, '队列')],
    } as any)
    const wrapper = mount(KnowledgePointSelector, { props: { subject: '数据结构' } })
    await flushPromises()

    expect(knowledgePointsApi.list).toHaveBeenCalledWith({ subject: '数据结构' })
    const options = wrapper.findAll('option').map((o) => o.text())
    expect(options).toContain('栈')
    expect(options).toContain('队列')
  })

  it('选择后发出 update:modelValue 与 select', async () => {
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({
      data: [kp(7, '栈')],
    } as any)
    const wrapper = mount(KnowledgePointSelector, { props: { subject: '数据结构' } })
    await flushPromises()

    await wrapper.find('select').setValue('7')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([7])
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ id: 7, name: '栈' })
  })

  it('无知识点时展示空态提示并禁用下拉', async () => {
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: [] } as any)
    const wrapper = mount(KnowledgePointSelector, { props: { subject: '数据结构' } })
    await flushPromises()

    expect(wrapper.text()).toContain('该学科暂未建立结构化知识点')
    expect(wrapper.find('select').attributes('disabled')).toBeDefined()
  })

  it('切换 subject 时重新加载', async () => {
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: [] } as any)
    const wrapper = mount(KnowledgePointSelector, { props: { subject: '数据结构' } })
    await flushPromises()
    await wrapper.setProps({ subject: '操作系统' })
    await flushPromises()

    expect(knowledgePointsApi.list).toHaveBeenLastCalledWith({ subject: '操作系统' })
  })

  it('excludeIds 过滤已关联知识点', async () => {
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({
      data: [kp(1, '栈'), kp(2, '队列')],
    } as any)
    const wrapper = mount(KnowledgePointSelector, {
      props: { subject: '数据结构', excludeIds: [1] },
    })
    await flushPromises()

    const options = wrapper.findAll('option').map((o) => o.text())
    expect(options).not.toContain('栈')
    expect(options).toContain('队列')
  })
})
