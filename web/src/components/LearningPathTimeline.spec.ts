import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import LearningPathTimeline from '@/components/LearningPathTimeline.vue'
import type { LearningPath, LearningPathStep, KnowledgePointBrief } from '@/types'

// MasteryBar 依赖 masteryLevel（纯函数），这里给出与真实实现一致的映射
vi.mock('@/api/mastery', () => ({
  masteryApi: {},
  masteryLevel: (score: number) => {
    const bounded = Math.max(0, Math.min(100, Math.round(score)))
    if (bounded >= 85) return { tone: 'strong', label: '掌握良好' }
    if (bounded >= 60) return { tone: 'steady', label: '稳步提升' }
    return { tone: 'weak', label: '需要加强' }
  },
}))

function brief(
  id: number,
  name: string,
  overrides: Partial<KnowledgePointBrief> = {},
): KnowledgePointBrief {
  return {
    id,
    name,
    subject: '数据结构',
    parent_id: null,
    node_type: 'concept',
    difficulty: 'easy',
    estimated_minutes: 20,
    ...overrides,
  }
}

function step(overrides: Partial<LearningPathStep> = {}): LearningPathStep {
  return {
    order: 1,
    knowledge_point: brief(1, '线性表'),
    mastery_score: 80,
    satisfied: true,
    is_target: false,
    ...overrides,
  }
}

function path(steps: LearningPathStep[], overrides: Partial<LearningPath> = {}): LearningPath {
  return {
    target: steps.find((s) => s.is_target)?.knowledge_point ?? brief(9, '目标'),
    ready: false,
    threshold: 70,
    steps,
    ...overrides,
  }
}

describe('LearningPathTimeline', () => {
  it('渲染路径标题、目标与各节点名称', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: {
        path: path([
          step({ order: 1, knowledge_point: brief(1, '线性表'), satisfied: true }),
          step({ order: 2, knowledge_point: brief(2, '栈'), satisfied: false, mastery_score: 40 }),
          step({
            order: 3,
            knowledge_point: brief(3, '表达式求值'),
            satisfied: false,
            mastery_score: null,
            is_target: true,
          }),
        ]),
      },
    })
    expect(wrapper.text()).toContain('目标：表达式求值')
    expect(wrapper.text()).toContain('掌握度 ≥ 70 视为已满足')
    expect(wrapper.findAll('.path-name').map((n) => n.text())).toEqual([
      '线性表',
      '栈',
      '表达式求值',
    ])
    // 目标徽标 + 第一个未满足节点标记为「当前」
    expect(wrapper.text()).toContain('目标')
    expect(wrapper.text()).toContain('当前')
  })

  it('多节点顺序按 order 升序渲染（输入乱序也正确）', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: {
        path: path([
          step({ order: 3, knowledge_point: brief(3, 'C'), is_target: true }),
          step({ order: 1, knowledge_point: brief(1, 'A') }),
          step({ order: 2, knowledge_point: brief(2, 'B') }),
        ]),
      },
    })
    expect(wrapper.findAll('.path-marker').map((n) => n.text())).toEqual(['1', '2', '3'])
    expect(wrapper.findAll('.path-name').map((n) => n.text())).toEqual(['A', 'B', 'C'])
  })

  it('区分 concept 与 container 节点类型', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: {
        path: path([
          step({ order: 1, knowledge_point: brief(1, '线性表', { node_type: 'container' }) }),
          step({ order: 2, knowledge_point: brief(2, '栈'), is_target: true }),
        ]),
      },
    })
    const chips = wrapper.findAll('.path-type-chip').map((n) => n.text())
    expect(chips).toEqual(['目录', '可学习'])
    expect(wrapper.text()).toContain('目录节点仅用于组织层级，不可直接练习')
  })

  it('空路径展示空态文案', () => {
    const wrapper = mount(LearningPathTimeline, { props: { path: null } })
    expect(wrapper.findAll('.path-step')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无可展示的学习路径')

    const custom = mount(LearningPathTimeline, {
      props: { path: null, emptyText: '暂无路径' },
    })
    expect(custom.text()).toContain('暂无路径')
  })

  it('steps 为空数组时同样展示空态', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: { path: path([], { target: brief(9, '空目标') }) },
    })
    expect(wrapper.findAll('.path-step')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无可展示的学习路径')
  })

  it('加载中展示加载文案而非空态', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: { path: null, loading: true },
    })
    expect(wrapper.text()).toContain('正在加载学习路径')
    expect(wrapper.text()).not.toContain('暂无可展示的学习路径')
  })

  it('掌握度缺失展示空态、解锁提示随状态变化', () => {
    const wrapper = mount(LearningPathTimeline, {
      props: {
        path: path([
          step({ order: 1, knowledge_point: brief(1, 'A'), satisfied: true }),
          step({
            order: 2,
            knowledge_point: brief(2, 'B'),
            satisfied: false,
            mastery_score: null,
            is_target: true,
          }),
        ]),
      },
    })
    expect(wrapper.text()).toContain('暂无掌握度记录')
    expect(wrapper.text()).toContain('已解锁')
    expect(wrapper.text()).toContain('前置已满足，可开始')
  })
})
