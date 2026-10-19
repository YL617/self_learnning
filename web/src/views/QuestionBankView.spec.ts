import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { questionsApi } from '@/api/questions'
import QuestionCard from '@/components/QuestionCard.vue'
import type { KnowledgePoint, Question } from '@/types'
import QuestionBankView from './QuestionBankView.vue'

vi.mock('@/api/knowledgePoints', () => ({ knowledgePointsApi: { list: vi.fn() } }))
vi.mock('@/api/questions', () => ({ questionsApi: { questionBank: vi.fn(), submitAnswer: vi.fn() } }))

const question: Question = {
  id: 31, subject: '数据结构', knowledge_point: '顺序表', question_type: 'choice',
  stem: '顺序表随机访问的时间复杂度是多少？', options_json: '["A. O(1)","B. O(n)"]',
  answer: 'A', analysis: '由下标计算元素地址，时间复杂度为O(1)。',
  source: 'admin', is_favorite: false, difficulty: 'easy', visibility: 'shared',
}
const concept: KnowledgePoint = {
  id: 11, name: '顺序表', subject: '数据结构', normalized_name: '顺序表',
  parent_id: null, description: null, node_type: 'concept', status: 'active', source: 'admin',
  created_at: '', updated_at: '',
}

async function setup(url = '/question-bank') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/question-bank', component: QuestionBankView },
    { path: '/questions', component: { template: '<div />' } },
  ] })
  await router.push(url)
  await router.isReady()
  const wrapper = mount(QuestionBankView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: [concept] } as never)
  vi.mocked(questionsApi.questionBank).mockResolvedValue({ data: [question] } as never)
  vi.mocked(questionsApi.submitAnswer).mockResolvedValue({ data: { is_correct: true } } as never)
})

describe('用户共享题库', () => {
  it('浏览已发布题目，不提前展示答案解析或管理控件', async () => {
    const { wrapper } = await setup()
    expect(questionsApi.questionBank).toHaveBeenCalledWith({ subject: undefined, difficulty: undefined, knowledge_point_id: undefined, limit: 100 })
    expect(wrapper.text()).toContain(question.stem)
    expect(wrapper.text()).not.toContain(question.analysis)
    expect(wrapper.findComponent(QuestionCard).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('删除题目')
    wrapper.unmount()
  })

  it('同步筛选到URL并消费知识点/学科/难度深链', async () => {
    const { wrapper, router } = await setup('/question-bank?subject=数据结构&knowledge_point_id=11&difficulty=easy')
    expect(questionsApi.questionBank).toHaveBeenLastCalledWith({ subject: '数据结构', difficulty: 'easy', knowledge_point_id: 11, limit: 100 })
    await wrapper.findAll('select')[1].setValue('hard')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.difficulty).toBe('hard')
    expect(questionsApi.questionBank).toHaveBeenLastCalledWith(expect.objectContaining({ difficulty: 'hard' }))
    await router.back()
    await flushPromises()
    expect(wrapper.findAll('select')[1].element.value).toBe('easy')
    wrapper.unmount()
  })

  it('更换学科清除旧知识点，重置恢复全部题目', async () => {
    const { wrapper, router } = await setup('/question-bank?subject=数据结构&knowledge_point_id=11')
    await wrapper.find('input').setValue('数学')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.knowledge_point_id).toBeUndefined()
    await wrapper.findAll('form button')[1].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    wrapper.unmount()
  })

  it('进入练习复用真实答题卡，作答成功后再显示解析', async () => {
    const { wrapper } = await setup()
    await wrapper.find('#bank-start-31').trigger('click')
    expect(wrapper.findComponent(QuestionCard).props('showManage')).toBe(false)
    await wrapper.find('input[type=radio]').setValue()
    const submit = wrapper.findAll('button').find(button => button.text().includes('提交答案'))!
    await submit.trigger('click')
    await flushPromises()
    expect(questionsApi.submitAnswer).toHaveBeenCalledWith(31, 'A')
    expect(wrapper.text()).toContain('本次答题记录已保存')
    const analysis = wrapper.findAll('button').find(button => button.text().includes('查看解析'))!
    await analysis.trigger('click')
    expect(wrapper.text()).toContain(question.analysis)
    await wrapper.find('.bank-practice-head button').trigger('click')
    expect(wrapper.findComponent(QuestionCard).exists()).toBe(false)
    expect(wrapper.find('#bank-start-31').exists()).toBe(true)
    wrapper.unmount()
  })

  it('作答请求失败保留重试且不伪造成功', async () => {
    vi.mocked(questionsApi.submitAnswer).mockRejectedValue(new Error('unavailable'))
    const { wrapper } = await setup()
    await wrapper.find('#bank-start-31').trigger('click')
    await wrapper.find('input[type=radio]').setValue()
    await wrapper.findAll('button').find(button => button.text().includes('提交答案'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('提交失败')
    expect(wrapper.text()).not.toContain('本次答题记录已保存')
    wrapper.unmount()
  })

  it('区分空题库与请求失败，失败可以重试', async () => {
    vi.mocked(questionsApi.questionBank).mockRejectedValueOnce(new Error('network'))
    const { wrapper } = await setup()
    expect(wrapper.find('[role=alert]').text()).toContain('加载失败')
    expect(wrapper.text()).not.toContain('暂无符合')
    vi.mocked(questionsApi.questionBank).mockResolvedValue({ data: [] } as never)
    await wrapper.find('[role=alert] button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('暂无符合条件的已发布题目')
    wrapper.unmount()
  })

  it('知识点失败不阻断题库读取，保留独立重试', async () => {
    vi.mocked(knowledgePointsApi.list).mockRejectedValue(new Error('network'))
    const { wrapper } = await setup()
    expect(wrapper.text()).toContain('知识点筛选暂不可用')
    expect(wrapper.text()).toContain(question.stem)
    wrapper.unmount()
  })

  it('拒绝无效知识点深链', async () => {
    const { wrapper } = await setup('/question-bank?knowledge_point_id=-3')
    expect(wrapper.text()).toContain('筛选条件无效')
    expect(questionsApi.questionBank).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('忽略过期请求，保持最新筛选结果', async () => {
    let resolveOld!: (value: never) => void
    vi.mocked(questionsApi.questionBank).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const { wrapper, router } = await setup()
    await router.push('/question-bank?difficulty=hard')
    await flushPromises()
    resolveOld({ data: [{ ...question, stem: '过期结果' }] } as never)
    await flushPromises()
    expect(wrapper.text()).toContain(question.stem)
    expect(wrapper.text()).not.toContain('过期结果')
    wrapper.unmount()
  })

  it('拒绝重复筛选参数而不是静默放宽查询', async () => {
    const { wrapper } = await setup('/question-bank?knowledge_point_id=11&knowledge_point_id=12')
    expect(wrapper.text()).toContain('筛选条件无效')
    expect(questionsApi.questionBank).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
