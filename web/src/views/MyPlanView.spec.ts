import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { masteryApi } from '@/api/mastery'
import { recommendationsApi } from '@/api/recommendations'
import type { MasterySummary, RecommendationItem } from '@/types'
import MyPlanView from './MyPlanView.vue'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

vi.mock('@/api/mastery', () => ({
  masteryApi: { summary: vi.fn() },
  masteryLevel: (score: number) => {
    const bounded = Math.max(0, Math.min(100, Math.round(score)))
    if (bounded >= 85) return { tone: 'strong', label: '掌握良好' }
    if (bounded >= 60) return { tone: 'steady', label: '稳步提升' }
    return { tone: 'weak', label: '需要加强' }
  },
}))

vi.mock('@/api/recommendations', () => ({
  recommendationsApi: { today: vi.fn() },
  actionTone: (action: string) => {
    const map: Record<string, { tone: string; icon: string }> = {
      review_wrong: { tone: 'danger', icon: '错题' },
      review_weak: { tone: 'amber', icon: '薄弱' },
      learn_new: { tone: 'teal', icon: '新知' },
      practice: { tone: 'neutral', icon: '加练' },
    }
    return map[action] ?? { tone: 'neutral', icon: '建议' }
  },
}))

function summary(overrides: Partial<MasterySummary> = {}): MasterySummary {
  return {
    total: 3,
    weak_count: 1,
    average_score: 62.4,
    today_review_count: 2,
    weak_threshold: 60,
    ...overrides,
  }
}

function item(overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    action: 'review_weak',
    action_label: '巩固薄弱知识点',
    knowledge_point_id: 3,
    knowledge_point_name: '链表',
    subject: '数据结构',
    score: 88.5,
    reason: '掌握度 42%，低于薄弱线 60%',
    order: 1,
    estimated_minutes: 20,
    components: { base: 72, gap: 1.35 },
    question_ids: [11],
    ...overrides,
  }
}

function mockPlan(items: RecommendationItem[], sum: MasterySummary) {
  vi.mocked(masteryApi.summary).mockResolvedValue({ data: sum } as any)
  vi.mocked(recommendationsApi.today).mockResolvedValue({
    data: { date: '2026-10-11', weak_threshold: 60, ready_threshold: 70, items },
  } as any)
}

async function setup(items: RecommendationItem[] = [item()], sum: MasterySummary = summary()) {
  mockPlan(items, sum)
  const wrapper = mount(MyPlanView)
  await flushPromises()
  return wrapper as VueWrapper<any>
}

describe('MyPlanView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染标题与区域 A 学习状态三指标', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).toContain('今日学习计划')
    expect(wrapper.text()).toContain('我的学习状态')
    expect(wrapper.findAll('.stat-value').map((node) => node.text())).toEqual([
      '3',
      '62%',
      '1',
    ])
    expect(wrapper.text()).toContain('已学习知识点')
    expect(wrapper.text()).toContain('平均掌握度 · 稳步提升')
    expect(wrapper.text()).toContain('薄弱知识点')
  })

  it('渲染推荐列表：类型、知识点、分数与理由', async () => {
    const wrapper = await setup()
    expect(wrapper.findAll('.plan-rec-item')).toHaveLength(1)
    expect(wrapper.find('.plan-rec-name').text()).toBe('链表')
    expect(wrapper.text()).toContain('巩固薄弱知识点')
    expect(wrapper.find('.plan-rec-reason').text()).toContain('掌握度 42%，低于薄弱线 60%')
    expect(wrapper.find('.plan-rec-score').text()).toContain('推荐分数 88.5')
    expect(wrapper.text()).toContain('约 20 分钟')
  })

  it('按 order 排序渲染多条推荐', async () => {
    const wrapper = await setup([
      item({ knowledge_point_id: 7, knowledge_point_name: '树', order: 2 }),
      item({ order: 1 }),
    ])
    const names = wrapper.findAll('.plan-rec-name').map((node) => node.text())
    expect(names).toEqual(['链表', '树'])
  })

  it('空数据状态正常（不报错且展示空态与提示）', async () => {
    const wrapper = await setup([], summary({ total: 0, weak_count: 0, average_score: 0 }))
    expect(wrapper.findAll('.stat-value').map((node) => node.text())).toEqual(['0', '0%', '0'])
    expect(wrapper.text()).toContain('还没有掌握度记录')
    expect(wrapper.text()).toContain('暂无学习建议')
    expect(wrapper.findAll('.plan-rec-item')).toHaveLength(0)
  })

  it('加载中展示加载文案而非空态', () => {
    mockPlan([], summary())
    const wrapper = mount(MyPlanView)
    expect(wrapper.text()).toContain('正在生成学习计划')
    expect(wrapper.text()).not.toContain('暂无学习建议')
  })

  it('点击「去练习」「查看知识点」跳转并携带知识点上下文', async () => {
    const wrapper = await setup()
    const buttons = wrapper.findAll('button')
    expect(buttons.map((btn) => btn.text())).toEqual(['去练习', '查看知识点'])

    await buttons[0].trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'questions',
      query: { knowledge_point_id: 3 },
    })

    await buttons[1].trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'knowledge',
      query: { knowledge_point_id: 3 },
    })
  })
})
