import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MasteryBar from './MasteryBar.vue'

describe('MasteryBar', () => {
  it('展示分数、等级与进度条宽度', () => {
    const wrapper = mount(MasteryBar, { props: { score: 72, label: '栈' } })

    expect(wrapper.text()).toContain('栈')
    expect(wrapper.text()).toContain('72%')
    expect(wrapper.text()).toContain('稳步提升')

    const track = wrapper.find('[role="progressbar"]')
    expect(track.attributes('aria-valuenow')).toBe('72')
    expect(wrapper.find('.mastery-fill').attributes('style')).toContain('width: 72%')
  })

  it('高分显示掌握良好，低分显示需要加强', () => {
    expect(mount(MasteryBar, { props: { score: 96 } }).text()).toContain('掌握良好')
    expect(mount(MasteryBar, { props: { score: 32 } }).text()).toContain('需要加强')
  })

  it('无记录时展示空态文案而不是 0%', () => {
    const wrapper = mount(MasteryBar, { props: { score: null } })
    expect(wrapper.text()).toContain('暂无掌握度记录')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('越界分数被夹取到 0~100', () => {
    const wrapper = mount(MasteryBar, { props: { score: 180 } })
    expect(wrapper.text()).toContain('100%')
    expect(wrapper.find('.mastery-fill').attributes('style')).toContain('width: 100%')

    const low = mount(MasteryBar, { props: { score: -30 } })
    expect(low.text()).toContain('0%')
  })
})
