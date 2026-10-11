import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RecommendationReason from './RecommendationReason.vue'

function item(overrides: Partial<{ reason: string; components: Record<string, number>; score: number }> = {}) {
  return {
    reason: '掌握度 42%，低于薄弱线 60%',
    components: {} as Record<string, number>,
    score: 88.5,
    ...overrides,
  }
}

describe('RecommendationReason', () => {
  it('有 reason 时逐条展示推荐原因', () => {
    const wrapper = mount(RecommendationReason, { props: { item: item() } })
    expect(wrapper.text()).toContain('推荐原因')
    expect(wrapper.findAll('.rec-reason-item')).toHaveLength(1)
    expect(wrapper.find('.rec-reason-item').text()).toBe('掌握度 42%，低于薄弱线 60%')
    expect(wrapper.find('.rec-reason-empty').exists()).toBe(false)
  })

  it('多因子 reason 按「；」拆分为多条理由', () => {
    const wrapper = mount(RecommendationReason, {
      props: {
        item: item({
          reason: '掌握度 45% 偏低；最近 5 次作答错了 3 次；学会它可以解锁 2 个后续知识点',
        }),
      },
    })
    const lines = wrapper.findAll('.rec-reason-item').map((node) => node.text())
    expect(lines).toEqual([
      '掌握度 45% 偏低',
      '最近 5 次作答错了 3 次',
      '学会它可以解锁 2 个后续知识点',
    ])
  })

  it('无 reason 时展示空态提示而非空白', () => {
    const wrapper = mount(RecommendationReason, { props: { item: item({ reason: '' }) } })
    expect(wrapper.findAll('.rec-reason-item')).toHaveLength(0)
    expect(wrapper.find('.rec-reason-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('系统暂未给出推荐理由')
  })

  it('item 为空（空状态）时不报错', () => {
    const wrapper = mount(RecommendationReason, { props: { item: null } })
    expect(wrapper.find('.rec-reason-empty').exists()).toBe(true)
    expect(wrapper.find('.rec-reason-factors').exists()).toBe(false)
  })

  it('展示打分依据（components 折叠）', () => {
    const wrapper = mount(RecommendationReason, {
      props: { item: item({ components: { base: 72, gap: 1.35 } }) },
    })
    const details = wrapper.find('.rec-reason-factors')
    expect(details.exists()).toBe(true)
    expect(details.text()).toContain('掌握度缺口 ×1.35')
    expect(details.text()).toContain('动作基础分 ×72.00')
    expect(details.text()).toContain('总分 88.5')
  })

  it('无 components 时不渲染打分依据', () => {
    const wrapper = mount(RecommendationReason, { props: { item: item() } })
    expect(wrapper.find('.rec-reason-factors').exists()).toBe(false)
  })
})
