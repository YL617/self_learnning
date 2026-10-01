import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { questionsApi } from '@/api/questions'
import type { KnowledgePoint, Question, QuestionKnowledgePoint } from '@/types'
import KnowledgePointSelector from './KnowledgePointSelector.vue'
import QuestionKnowledgePointsModal from './QuestionKnowledgePointsModal.vue'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: { list: vi.fn() },
  toKnowledgePointNameMap: (items: { id: number; name: string }[]) =>
    Object.fromEntries(items.map((item) => [item.id, item.name])),
}))

vi.mock('@/api/questions', () => ({
  questionsApi: {
    getQuestionKnowledgePoints: vi.fn(),
    attachQuestionKnowledgePoint: vi.fn(),
    setPrimaryKnowledgePoint: vi.fn(),
    detachQuestionKnowledgePoint: vi.fn(),
  },
}))

const question: Question = {
  id: 1,
  subject: '数据结构',
  knowledge_point: '栈和队列',
  question_type: 'choice',
  stem: '题干',
  options_json: null,
  answer: 'A',
  analysis: null,
  source: 'ai',
  is_favorite: false,
}

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

function assoc(id: number, kpId: number, role: string): QuestionKnowledgePoint {
  return {
    id,
    question_id: 1,
    knowledge_point_id: kpId,
    role,
    source: 'manual',
    created_at: '2026-10-01T00:00:00',
  }
}

function mountModal() {
  return mount(QuestionKnowledgePointsModal, {
    props: { open: true, question },
    global: { stubs: { teleport: true } },
  })
}

describe('QuestionKnowledgePointsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(knowledgePointsApi.list).mockResolvedValue({
      data: [kp(1, '栈'), kp(2, '队列')],
    } as any)
  })

  it('打开时加载关联并以名称展示', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockResolvedValue({
      data: [assoc(10, 1, 'primary')],
    } as any)
    const wrapper = mountModal()
    await flushPromises()

    expect(questionsApi.getQuestionKnowledgePoints).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('栈')
    expect(wrapper.emitted('updated')?.at(-1)?.[1]).toHaveLength(1)
  })

  it('无 primary 时新增默认为 primary', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockResolvedValue({ data: [] } as any)
    vi.mocked(questionsApi.attachQuestionKnowledgePoint).mockResolvedValue({
      data: assoc(11, 2, 'primary'),
    } as any)
    const wrapper = mountModal()
    await flushPromises()

    wrapper.findComponent(KnowledgePointSelector).vm.$emit('update:modelValue', 2)
    await nextTick()
    const addButton = wrapper.findAll('button').find((b) => b.text().includes('添加'))
    await addButton!.trigger('click')
    await flushPromises()

    expect(questionsApi.attachQuestionKnowledgePoint).toHaveBeenCalledWith(1, {
      knowledge_point_id: 2,
      role: 'primary',
    })
  })

  it('已存在 primary 时新增默认为 secondary', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockResolvedValue({
      data: [assoc(10, 1, 'primary')],
    } as any)
    vi.mocked(questionsApi.attachQuestionKnowledgePoint).mockResolvedValue({
      data: assoc(11, 2, 'secondary'),
    } as any)
    const wrapper = mountModal()
    await flushPromises()

    wrapper.findComponent(KnowledgePointSelector).vm.$emit('update:modelValue', 2)
    await nextTick()
    const addButton = wrapper.findAll('button').find((b) => b.text().includes('添加'))
    await addButton!.trigger('click')
    await flushPromises()

    expect(questionsApi.attachQuestionKnowledgePoint).toHaveBeenCalledWith(1, {
      knowledge_point_id: 2,
      role: 'secondary',
    })
  })

  it('设为主知识点调用 setPrimary（单次请求，由后端保证事务）', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockResolvedValue({
      data: [assoc(10, 1, 'primary'), assoc(11, 2, 'secondary')],
    } as any)
    vi.mocked(questionsApi.setPrimaryKnowledgePoint).mockResolvedValue({
      data: assoc(11, 2, 'primary'),
    } as any)
    const wrapper = mountModal()
    await flushPromises()

    const primaryButton = wrapper.findAll('button').find((b) => b.text().includes('设为主'))
    await primaryButton!.trigger('click')
    await flushPromises()

    expect(questionsApi.setPrimaryKnowledgePoint).toHaveBeenCalledWith(1, 2)
  })

  it('移除关联调用 detach', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockResolvedValue({
      data: [assoc(10, 1, 'primary')],
    } as any)
    vi.mocked(questionsApi.detachQuestionKnowledgePoint).mockResolvedValue({ data: undefined } as any)
    const wrapper = mountModal()
    await flushPromises()

    const removeButton = wrapper.find('button[title="移除关联"]')
    await removeButton.trigger('click')
    await flushPromises()

    expect(questionsApi.detachQuestionKnowledgePoint).toHaveBeenCalledWith(1, 1)
  })

  it('SubjectMismatch(400) 展示后端可读提示', async () => {
    vi.mocked(questionsApi.getQuestionKnowledgePoints).mockRejectedValue({
      response: { status: 400, data: { detail: '知识点与题目学科不一致' } },
    } as any)
    const wrapper = mountModal()
    await flushPromises()

    expect(wrapper.text()).toContain('知识点与题目学科不一致')
  })
})
