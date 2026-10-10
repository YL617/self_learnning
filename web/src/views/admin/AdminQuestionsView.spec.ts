import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { adminApi } from '@/api/admin'
import { knowledgePointsApi } from '@/api/knowledgePoints'
import type { AdminQuestion, KnowledgeCoverage, KnowledgePoint } from '@/types'
import AdminQuestionsView from './AdminQuestionsView.vue'

vi.mock('@/api/admin', () => ({
  adminApi: {
    questions: vi.fn(),
    deleteQuestion: vi.fn(),
    createQuestion: vi.fn(),
    getQuestion: vi.fn(),
    attachQuestionKnowledgePoint: vi.fn(),
    knowledgeCoverage: vi.fn(),
  },
}))

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: {
    list: vi.fn(),
  },
}))

function kp(id: number, name: string): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject: '数据结构',
    parent_id: null,
    description: null,
    status: 'active',
    source: 'system',
    node_type: 'concept',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
  }
}

function adminQuestion(id: number, overrides: Partial<AdminQuestion> = {}): AdminQuestion {
  return {
    id,
    user_id: 1,
    subject: '数据结构',
    knowledge_point: '栈',
    question_type: 'choice',
    stem: `题目 ${id} 的题干`,
    source: 'admin',
    is_favorite: false,
    difficulty: 'easy',
    visibility: 'shared',
    created_at: '2026-10-10T00:00:00',
    ...overrides,
  }
}

const coverage: KnowledgeCoverage = {
  concept_total: 56,
  covered: 12,
  uncovered: 44,
  question_total: 20,
  items: [
    { subject: '数据结构', concept_total: 56, covered: 12, uncovered: 44, question_total: 20 },
  ],
}

async function setup(items: AdminQuestion[] = [adminQuestion(1), adminQuestion(2, { visibility: 'private' })]) {
  vi.mocked(adminApi.questions).mockResolvedValue({ data: items } as any)
  vi.mocked(adminApi.knowledgeCoverage).mockResolvedValue({ data: coverage } as any)
  vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: [kp(9, '循环单链表')] } as any)
  const wrapper = mount(AdminQuestionsView)
  await flushPromises()
  return wrapper as VueWrapper<any>
}

describe('AdminQuestionsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('渲染知识覆盖统计（只统计 concept 口径）', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).toContain('可学习知识点 56 个')
    expect(wrapper.text()).toContain('已有题目覆盖 12 个')
    expect(wrapper.text()).toContain('21%')
    expect(wrapper.find('.admin-table').exists()).toBe(true)
    expect(adminApi.knowledgeCoverage).toHaveBeenCalled()
  })

  it('题目列表展示难度与可见性徽标', async () => {
    const wrapper = await setup()
    const badges = wrapper.findAll('.badge').map((b: any) => b.text())
    expect(badges.some((text: string) => text.includes('共享'))).toBe(true)
    expect(badges.some((text: string) => text.includes('私有'))).toBe(true)
    expect(badges.some((text: string) => text.includes('简单'))).toBe(true)
  })

  it('创建题目提交完整载荷（含难度/可见性/知识点绑定）', async () => {
    vi.mocked(adminApi.createQuestion).mockResolvedValue({ data: adminQuestion(99) } as any)
    const wrapper = await setup()

    // 表单栅格：第 1 个 input = 学科，第 2 个 input = 知识点文本。
    await wrapper.findAll('.input')[1].setValue('循环单链表')
    // textarea 顺序：题干 / 选项(choice) / 答案 / 解析。
    await wrapper.findAll('.textarea')[0].setValue('新题目的题干')
    await wrapper.findAll('.textarea')[2].setValue('A')

    const buttons = wrapper.findAll('button')
    const createBtn = buttons.find((btn: any) => btn.text().includes('创建题目'))
    await createBtn!.trigger('click')
    await flushPromises()

    expect(adminApi.createQuestion).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(adminApi.createQuestion).mock.calls[0][0]
    expect(payload.stem).toBe('新题目的题干')
    expect(payload.answer).toBe('A')
    expect(payload.subject).toBe('数据结构')
    expect(payload.visibility).toBe('shared')
    expect(payload.knowledge_point).toBe('循环单链表')
  })

  it('题干或答案为空时不提交', async () => {
    const wrapper = await setup()
    const buttons = wrapper.findAll('button')
    const createBtn = buttons.find((btn: any) => btn.text().includes('创建题目'))
    await createBtn!.trigger('click')
    await flushPromises()
    expect(adminApi.createQuestion).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('题干与答案不能为空')
  })

  it('点击详情懒加载题目详情（含关联知识点）', async () => {
    vi.mocked(adminApi.getQuestion).mockResolvedValue({
      data: {
        ...adminQuestion(1),
        options_json: null,
        answer: 'A',
        analysis: '解析内容',
        knowledge_points: [
          {
            id: 1,
            question_id: 1,
            knowledge_point_id: 9,
            role: 'primary',
            source: 'manual',
            created_at: '2026-10-10T00:00:00',
          },
        ],
      },
    } as any)
    const wrapper = await setup()
    const detailBtn = wrapper.findAll('button').find((btn: any) => btn.text() === '详情')
    await detailBtn!.trigger('click')
    await flushPromises()

    expect(adminApi.getQuestion).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('参考答案：A')
    expect(wrapper.text()).toContain('循环单链表')
  })

  it('删除题目后刷新覆盖统计', async () => {
    vi.mocked(adminApi.deleteQuestion).mockResolvedValue({ data: undefined } as any)
    const wrapper = await setup()
    vi.mocked(adminApi.knowledgeCoverage).mockClear()
    const removeBtn = wrapper.findAll('button').find((btn: any) => btn.text().includes('删除'))
    await removeBtn!.trigger('click')
    await flushPromises()

    expect(adminApi.deleteQuestion).toHaveBeenCalledWith(1)
    expect(adminApi.knowledgeCoverage).toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('题目 1 的题干')
  })
})
