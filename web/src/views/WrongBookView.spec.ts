import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { questionsApi } from '@/api/questions'
import type { Question, WrongBookItem } from '@/types'
import WrongBookView from './WrongBookView.vue'

vi.mock('@/api/questions', () => ({
  questionsApi: {
    wrongBook: vi.fn(),
    dueWrongBook: vi.fn(),
    updateWrongItem: vi.fn(),
    reviewWrongItem: vi.fn(),
    generate: vi.fn(),
  },
}))

vi.mock('@/utils/petEvents', () => ({ petEvents: { emit: vi.fn() } }))

function question(id: number): Question {
  return {
    id,
    subject: '数据结构',
    knowledge_point: '栈',
    question_type: 'choice',
    stem: `题目 ${id}`,
    options_json: null,
    answer: 'A',
    analysis: null,
    source: 'ai',
    is_favorite: false,
  }
}

function item(overrides: Partial<WrongBookItem> = {}): WrongBookItem {
  return {
    id: 1,
    question_id: 100,
    review_count: 1,
    mastered: false,
    review_stage: 2,
    next_review_date: '2026-10-01',
    last_reviewed_at: null,
    created_at: '2026-09-30T00:00:00',
    question: question(100),
    ...overrides,
  }
}

function mountView() {
  return mount(WrongBookView)
}

describe('WrongBookView（大阶段 2 复习队列）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(questionsApi.wrongBook).mockResolvedValue({ data: [item()] } as any)
    vi.mocked(questionsApi.dueWrongBook).mockResolvedValue({
      data: [item({ id: 2, question_id: 200, question: question(200), next_review_date: '2026-09-20' })],
    } as any)
    vi.mocked(questionsApi.reviewWrongItem).mockResolvedValue({ data: item() } as any)
    vi.mocked(questionsApi.updateWrongItem).mockResolvedValue({
      data: item({ mastered: true }),
    } as any)
  })

  it('展示复习阶段、下次复习日期与今日需要复习提示', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('阶段 2/5')
    expect(wrapper.text()).toContain('下次复习：2026-10-01')
    expect(wrapper.text()).toContain('今日需要复习 1 题')
    expect(wrapper.text()).toContain('今日需要复习')
  })

  it('可切换到只看今日需要复习', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('题目 100')
    expect(wrapper.text()).not.toContain('题目 200')

    const toggle = wrapper.findAll('button').find((b) => b.text().includes('全部错题'))!
    await toggle.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('只看今日需要复习')
    expect(wrapper.text()).toContain('题目 200')
    expect(wrapper.text()).not.toContain('题目 100')
  })

  it('复习一次调用后端 reviewed 语义的接口并刷新', async () => {
    const wrapper = mountView()
    await flushPromises()

    const reviewBtn = wrapper.findAll('button').find((b) => b.text().includes('复习一次'))!
    await reviewBtn.trigger('click')
    await flushPromises()

    expect(questionsApi.reviewWrongItem).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('已完成一次复习，下次复习时间已更新')
  })

  it('标记已掌握走 mastered 语义', async () => {
    const wrapper = mountView()
    await flushPromises()

    const masterBtn = wrapper.findAll('button').find((b) => b.text().includes('标记已掌握'))!
    await masterBtn.trigger('click')
    await flushPromises()

    expect(questionsApi.updateWrongItem).toHaveBeenCalledWith(1, true)
  })

  it('已掌握的错题不再展示复习按钮', async () => {
    vi.mocked(questionsApi.wrongBook).mockResolvedValue({
      data: [item({ mastered: true })],
    } as any)
    vi.mocked(questionsApi.dueWrongBook).mockResolvedValue({ data: [] } as any)

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('已掌握')
    expect(wrapper.findAll('button').some((b) => b.text().includes('复习一次'))).toBe(false)
    expect(wrapper.text()).toContain('已掌握，不再进入复习队列')
    expect(wrapper.text()).not.toContain('今日需要复习 1 题')
  })

  it('接口失败时展示可读错误而不是崩溃', async () => {
    vi.mocked(questionsApi.reviewWrongItem).mockRejectedValue({
      response: { data: { detail: '该错题已标记为掌握，无需重复复习' } },
    })

    const wrapper = mountView()
    await flushPromises()
    const reviewBtn = wrapper.findAll('button').find((b) => b.text().includes('复习一次'))!
    await reviewBtn.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('该错题已标记为掌握，无需重复复习')
  })
})
