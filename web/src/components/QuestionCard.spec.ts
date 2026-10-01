import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Question } from '@/types'
import QuestionCard from './QuestionCard.vue'

vi.mock('@/api/questions', () => ({
  questionsApi: { submitAnswer: vi.fn() },
}))

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 1,
    subject: '数据结构',
    knowledge_point: '栈和队列',
    question_type: 'choice',
    stem: '以下哪个是后进先出？',
    options_json: null,
    answer: '栈',
    analysis: null,
    source: 'legacy',
    is_favorite: false,
    ...overrides,
  }
}

describe('QuestionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('存在结构化关联时优先展示标签，主知识点带 [主] 标记', () => {
    const wrapper = mount(QuestionCard, {
      props: {
        question: question(),
        knowledgePointTags: [
          { id: 2, name: '队列', role: 'secondary' },
          { id: 1, name: '栈', role: 'primary' },
        ],
      },
    })
    const tags = wrapper.findAll('.question-tags .badge').map((b) => b.text())
    expect(tags[0]).toContain('[主]')
    expect(tags[0]).toContain('栈')
    expect(tags).toContain('队列')
    // 不应回退到旧文本
    expect(wrapper.text()).not.toContain('栈和队列')
  })

  it('无结构化关联时回退展示 legacy knowledge_point 文本', () => {
    const wrapper = mount(QuestionCard, {
      props: { question: question({ knowledge_point: '栈和队列' }) },
    })
    expect(wrapper.find('.question-tags').text()).toContain('栈和队列')
  })

  it('showManage 时展示「知识点」入口并发出 manage 事件', async () => {
    const wrapper = mount(QuestionCard, {
      props: { question: question(), showManage: true },
    })
    const manageButton = wrapper.findAll('button').find((b) => b.text().includes('知识点'))
    expect(manageButton).toBeTruthy()
    await manageButton!.trigger('click')
    expect(wrapper.emitted('manage')?.[0]?.[0]).toMatchObject({ id: 1 })
  })
})
