import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { questionsApi } from '@/api/questions'
import type { KnowledgePoint, Question, QuestionKnowledgePoint } from '@/types'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import QuestionsView from './QuestionsView.vue'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: { list: vi.fn() },
  toKnowledgePointNameMap: (items: { id: number; name: string }[]) =>
    Object.fromEntries(items.map((item) => [item.id, item.name])),
}))

vi.mock('@/api/questions', () => ({
  questionsApi: {
    list: vi.fn(),
    generate: vi.fn(),
    getQuestionKnowledgePoints: vi.fn(),
    setFavorite: vi.fn(),
    remove: vi.fn(),
  },
}))

const stQuestions: Question[] = [
  {
    id: 100,
    subject: '数据结构',
    knowledge_point: '栈和队列',
    question_type: 'choice',
    stem: 'legacy 题',
    options_json: null,
    answer: 'A',
    analysis: null,
    source: 'legacy',
    is_favorite: false,
  },
  {
    id: 101,
    subject: '数据结构',
    knowledge_point: '树',
    question_type: 'choice',
    stem: '结构化题',
    options_json: null,
    answer: 'B',
    analysis: null,
    source: 'ai',
    is_favorite: false,
  },
]

function kp(id: number, name: string): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject: '数据结构',
    parent_id: null,
    description: null,
    status: 'active',
    source: 'admin',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
  }
}

function assoc(questionId: number, kpId: number, role: string): QuestionKnowledgePoint {
  return {
    id: questionId * 10 + kpId,
    question_id: questionId,
    knowledge_point_id: kpId,
    role,
    source: 'manual',
    created_at: '2026-10-01T00:00:00',
  }
}

function mountView() {
  return mount(QuestionsView, { global: { stubs: { teleport: true } } })
}

describe('QuestionsView（Phase 2 集成）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: [kp(1, '栈')] } as any)
    vi.mocked(questionsApi.list).mockResolvedValue({ data: stQuestions } as any)
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockImplementation(
      async (questionId: number) => ({ data: questionId === 101 ? [assoc(101, 1, 'primary')] : [] }) as any,
    )
    vi.mocked(questionsApi.generate).mockResolvedValue({ data: [] } as any)
  })

  it('未选择结构化知识点时，旧行为不变（不发送 knowledge_point_id）', async () => {
    const wrapper = mountView()
    await flushPromises()

    const genButton = wrapper.findAll('button').find((b) => b.text().includes('生成题目'))
    await genButton!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(questionsApi.generate).mock.calls[0][0]
    expect(payload.knowledge_point_id).toBeUndefined()
    expect(payload.knowledge_point).toBe('栈和队列')
  })

  it('选择结构化知识点后发送 knowledge_point_id 并回填显示名称', async () => {
    const wrapper = mountView()
    await flushPromises()

    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    const genButton = wrapper.findAll('button').find((b) => b.text().includes('生成题目'))
    await genButton!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(questionsApi.generate).mock.calls[0][0]
    expect(payload.knowledge_point_id).toBe(1)
    expect(payload.knowledge_point).toBe('栈')
  })

  it('结构化关联优先展示标签，无关联时回退 legacy 文本', async () => {
    const wrapper = mountView()
    await flushPromises()

    const cards = wrapper.findAll('.question-card')
    expect(cards).toHaveLength(2)
    // 第一条：legacy 回退
    expect(cards[0].find('.question-tags').text()).toContain('栈和队列')
    // 第二条：结构化标签
    expect(cards[1].find('.question-tags').text()).toContain('栈')
  })
})
