import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import PrerequisiteEditor from '@/components/PrerequisiteEditor.vue'
import type { KnowledgePoint, LearningPath, PrerequisiteDetail } from '@/types'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: {
    list: vi.fn(),
    prerequisites: vi.fn(),
    addPrerequisite: vi.fn(),
    removePrerequisite: vi.fn(),
    learningPath: vi.fn(),
    suggestPrerequisites: vi.fn(),
  },
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

function detail(items: PrerequisiteDetail['items'], ready = false): PrerequisiteDetail {
  return {
    knowledge_point: { id: 2, name: '树', subject: '数据结构', parent_id: null },
    ready,
    threshold: 70,
    items,
  }
}

function path(): LearningPath {
  return {
    target: { id: 3, name: '二叉树', subject: '数据结构', parent_id: null },
    ready: false,
    threshold: 70,
    steps: [
      {
        order: 1,
        knowledge_point: { id: 1, name: '链表', subject: '数据结构', parent_id: null },
        mastery_score: 82,
        satisfied: true,
        is_target: false,
      },
      {
        order: 2,
        knowledge_point: { id: 3, name: '二叉树', subject: '数据结构', parent_id: null },
        mastery_score: null,
        satisfied: false,
        is_target: true,
      },
    ],
  }
}

async function setup(items: PrerequisiteDetail['items'] = []) {
  vi.mocked(knowledgePointsApi.prerequisites).mockResolvedValue({ data: detail(items) } as any)
  vi.mocked(knowledgePointsApi.learningPath).mockResolvedValue({ data: path() } as any)
  vi.mocked(knowledgePointsApi.list).mockResolvedValue({
    data: [kp(1, '链表'), kp(2, '树'), kp(3, '二叉树')],
  } as any)
  const wrapper = mount(PrerequisiteEditor, { props: { knowledgePointId: 2 } })
  await flushPromises()
  return wrapper
}

describe('PrerequisiteEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('展示前置列表与满足状态', async () => {
    const wrapper = await setup([
      {
        id: 1,
        knowledge_point_id: 2,
        prerequisite_id: 1,
        strength: 80,
        source: 'manual',
        status: 'active',
        note: null,
        created_at: '2026-10-01T00:00:00',
        updated_at: '2026-10-01T00:00:00',
        prerequisite: { id: 1, name: '链表', subject: '数据结构', parent_id: null },
        satisfied: false,
        blocking: true,
      },
    ])
    expect(wrapper.text()).toContain('前置知识')
    expect(wrapper.text()).toContain('链表')
    expect(wrapper.text()).toContain('未满足（硬前置）')
    expect(wrapper.text()).toContain('存在未满足的硬前置')
  })

  it('展示学习路径的拓扑顺序', async () => {
    const wrapper = await setup()
    const steps = wrapper.findAll('.prereq-path li').map((node) => node.text())
    expect(steps[0]).toContain('链表')
    expect(steps[0]).toContain('掌握度 82%')
    expect(steps[1]).toContain('二叉树')
    expect(steps[1]).toContain('目标')
  })

  it('候选下拉排除自身与已存在的前置', async () => {
    const wrapper = await setup([
      {
        id: 1,
        knowledge_point_id: 2,
        prerequisite_id: 1,
        strength: 100,
        source: 'manual',
        status: 'active',
        note: null,
        created_at: '2026-10-01T00:00:00',
        updated_at: '2026-10-01T00:00:00',
        prerequisite: { id: 1, name: '链表', subject: '数据结构', parent_id: null },
        satisfied: true,
        blocking: false,
      },
    ])
    // 精确比对选项：应只剩「二叉树」，自身（树）与已存在前置（链表）都要被排除。
    const options = wrapper.findAll('select option').map((node) => node.text().trim())
    expect(options).toEqual(['选择前置知识点', '二叉树（数据结构）'])
  })

  it('添加前置后重新加载并向上通知', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.addPrerequisite).mockResolvedValue({ data: {} } as any)
    await wrapper.find('select').setValue('1')
    await wrapper.find('.prereq-form button').trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.addPrerequisite).toHaveBeenCalledWith(2, {
      prerequisite_id: 1,
      strength: 100,
      note: null,
    })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('添加成环时展示后端中文错误', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.addPrerequisite).mockRejectedValue({
      response: { data: { detail: '该前置关系会形成循环依赖，已拒绝' } },
    })
    await wrapper.find('select').setValue('3')
    await wrapper.find('.prereq-form button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('该前置关系会形成循环依赖，已拒绝')
  })

  it('删除前置调用 remove 并刷新', async () => {
    const wrapper = await setup([
      {
        id: 1,
        knowledge_point_id: 2,
        prerequisite_id: 1,
        strength: 100,
        source: 'manual',
        status: 'active',
        note: null,
        created_at: '2026-10-01T00:00:00',
        updated_at: '2026-10-01T00:00:00',
        prerequisite: { id: 1, name: '链表', subject: '数据结构', parent_id: null },
        satisfied: true,
        blocking: false,
      },
    ])
    vi.mocked(knowledgePointsApi.removePrerequisite).mockResolvedValue({ data: undefined } as any)
    await wrapper.find('.prereq-list button').trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.removePrerequisite).toHaveBeenCalledWith(2, 1)
  })

  it('AI 提议只展示、不落库；点击采纳后才建立关系', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.suggestPrerequisites).mockResolvedValue({
      data: {
        knowledge_point: { id: 2, name: '树', subject: '数据结构', parent_id: null },
        suggestions: [
          { prerequisite_id: 1, prerequisite_name: '链表', reason: '树依赖链表', confidence: 0.9 },
        ],
        note: null,
      },
    } as any)
    vi.mocked(knowledgePointsApi.addPrerequisite).mockResolvedValue({ data: {} } as any)

    const aiButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('AI 提议'))!
    await aiButton.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('树依赖链表')
    // 仅提议、尚未落库
    expect(knowledgePointsApi.addPrerequisite).not.toHaveBeenCalled()

    const adopt = wrapper
      .findAll('button')
      .find((button) => button.text().includes('采纳'))!
    await adopt.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.addPrerequisite).toHaveBeenCalledWith(2, {
      prerequisite_id: 1,
      strength: 100,
      note: 'AI 建议：树依赖链表',
    })
  })
})
