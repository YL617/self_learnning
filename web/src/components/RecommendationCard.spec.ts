import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RecommendationCard from '@/components/RecommendationCard.vue'
import type { RecommendationItem } from '@/types'

function item(overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    action: 'review_weak',
    action_label: '巩固薄弱知识点',
    knowledge_point_id: 3,
    knowledge_point_name: '链表',
    subject: '数据结构',
    score: 78.4,
    reason: '掌握度 42%，低于薄弱线 60%；学会它可以解锁 2 个后续知识点',
    order: 1,
    estimated_minutes: 20,
    components: { base: 72, gap: 1.35, unlock: 1.24 },
    question_ids: [11],
    ...overrides,
  }
}

describe('RecommendationCard', () => {
  it('按 order 排序渲染建议与理由', () => {
    const wrapper = mount(RecommendationCard, {
      props: {
        items: [
          item({ knowledge_point_id: 5, knowledge_point_name: '树', order: 2 }),
          item({ order: 1 }),
        ],
      },
    })
    const names = wrapper.findAll('.rec-name').map((node) => node.text())
    expect(names).toEqual(['链表', '树'])
    expect(wrapper.text()).toContain('掌握度 42%，低于薄弱线 60%')
    expect(wrapper.text()).toContain('巩固薄弱知识点')
    expect(wrapper.text()).toContain('约 20 分钟')
  })

  it('打分依据可展开且展示分解项中文名', () => {
    const wrapper = mount(RecommendationCard, { props: { items: [item()] } })
    const details = wrapper.find('.rec-factors')
    expect(details.exists()).toBe(true)
    expect(details.text()).toContain('动作基础分')
    expect(details.text()).toContain('解锁加成')
    expect(details.text()).toContain('总分 78.4')
  })

  it('空列表展示可解释的空态文案', () => {
    const wrapper = mount(RecommendationCard, { props: { items: [] } })
    expect(wrapper.findAll('.rec-item')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无学习建议')
  })

  it('点击开始向上抛出对应建议', async () => {
    const target = item({ action: 'review_wrong', action_label: '复习错题' })
    const wrapper = mount(RecommendationCard, { props: { items: [target] } })
    await wrapper.find('button').trigger('click')
    const emitted = wrapper.emitted('start')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(target)
  })

  it('加载中不展示空态', () => {
    const wrapper = mount(RecommendationCard, { props: { items: [], loading: true } })
    expect(wrapper.text()).toContain('正在生成建议')
    expect(wrapper.text()).not.toContain('暂无学习建议')
  })
})
