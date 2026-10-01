import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { masteryApi } from '@/api/mastery'
import { questionsApi } from '@/api/questions'
import type { KnowledgePoint, KnowledgePointMastery, Question, QuestionKnowledgePoint } from '@/types'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import QuestionCard from '@/components/QuestionCard.vue'
import QuestionsView from './QuestionsView.vue'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: {
    list: vi.fn(),
    prerequisites: vi.fn(),
    addPrerequisite: vi.fn(),
    removePrerequisite: vi.fn(),
    learningPath: vi.fn(),
    suggestPrerequisites: vi.fn(),
  },
  toKnowledgePointNameMap: (items: { id: number; name: string }[]) =>
    Object.fromEntries(items.map((item) => [item.id, item.name])),
}))

vi.mock('@/api/mastery', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/mastery')>()),
  masteryApi: { get: vi.fn(), list: vi.fn(), weak: vi.fn(), summary: vi.fn() },
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

function mastery(kpId: number, score: number): KnowledgePointMastery {
  return {
    id: kpId,
    knowledge_point_id: kpId,
    mastery_score: score,
    attempt_count: 3,
    correct_count: 2,
    correct_streak: 1,
    last_answered_at: '2026-10-01T00:00:00',
    last_correct_at: '2026-10-01T00:00:00',
    last_reviewed_at: null,
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
    knowledge_point: { id: kpId, name: '栈', subject: '数据结构', parent_id: null },
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
    vi.mocked(masteryApi.get).mockResolvedValue({ data: mastery(1, 72) } as any)
    vi.mocked(knowledgePointsApi.prerequisites).mockResolvedValue({
      data: {
        knowledge_point: { id: 1, name: '栈', subject: '数据结构', parent_id: null },
        ready: true,
        threshold: 70,
        items: [],
      },
    } as any)
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

  it('选中知识点后展示该知识点的掌握度', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.mastery-bar').exists()).toBe(false)

    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    expect(masteryApi.get).toHaveBeenCalledWith(1)
    expect(wrapper.find('.mastery-bar').text()).toContain('72%')
  })

  it('尚未产生掌握度记录（404）时展示空态而非报错', async () => {
    vi.mocked(masteryApi.get).mockRejectedValue({ response: { status: 404 } })

    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    expect(wrapper.find('.mastery-bar').text()).toContain('暂无掌握度记录')
    expect(wrapper.text()).not.toContain('生成失败')
  })

  it('答题后局部刷新掌握度', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()
    expect(masteryApi.get).toHaveBeenCalledTimes(1)

    vi.mocked(masteryApi.get).mockResolvedValue({ data: mastery(1, 88) } as any)
    wrapper.findAllComponents(QuestionCard)[0].vm.$emit('answered', stQuestions[0], true)
    await flushPromises()

    expect(masteryApi.get).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.mastery-bar').text()).toContain('88%')
  })

  it('存在前置知识时提示「还要先学什么」，并区分是否已满足', async () => {
    vi.mocked(knowledgePointsApi.prerequisites).mockResolvedValue({
      data: {
        knowledge_point: { id: 1, name: '栈', subject: '数据结构', parent_id: null },
        ready: false,
        threshold: 70,
        items: [
          {
            id: 11,
            knowledge_point_id: 1,
            prerequisite_id: 2,
            strength: 100,
            source: 'manual',
            status: 'active',
            note: null,
            created_at: '2026-10-01T00:00:00',
            updated_at: '2026-10-01T00:00:00',
            prerequisite: { id: 2, name: '链表', subject: '数据结构', parent_id: null },
            satisfied: false,
            blocking: true,
          },
          {
            id: 12,
            knowledge_point_id: 1,
            prerequisite_id: 3,
            strength: 30,
            source: 'manual',
            status: 'active',
            note: null,
            created_at: '2026-10-01T00:00:00',
            updated_at: '2026-10-01T00:00:00',
            prerequisite: { id: 3, name: '数组', subject: '数据结构', parent_id: null },
            satisfied: false,
            blocking: false,
          },
        ],
      },
    } as any)

    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    const hint = wrapper.find('.prereq-hint')
    expect(hint.exists()).toBe(true)
    expect(knowledgePointsApi.prerequisites).toHaveBeenCalledWith(1)
    expect(hint.text()).toContain('前置知识')
    expect(hint.text()).toContain('链表')
    expect(hint.text()).toContain('未满足')
    expect(hint.text()).toContain('数组')
    expect(hint.text()).toContain('建议先学')
  })

  it('没有前置知识时不展示前置提示（旧行为不变）', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    expect(wrapper.find('.prereq-hint').exists()).toBe(false)
  })

  it('前置知识接口失败时静默降级，不影响掌握度展示', async () => {
    vi.mocked(knowledgePointsApi.prerequisites).mockRejectedValue(new Error('boom'))

    const wrapper = mountView()
    await flushPromises()
    wrapper.findComponent(KnowledgePointSelector).vm.$emit('select', kp(1, '栈'))
    await flushPromises()

    expect(wrapper.find('.prereq-hint').exists()).toBe(false)
    expect(wrapper.find('.mastery-bar').text()).toContain('72%')
  })
})
