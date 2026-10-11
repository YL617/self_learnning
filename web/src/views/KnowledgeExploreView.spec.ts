import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { masteryApi } from '@/api/mastery'
import type { KnowledgePoint, Question } from '@/types'
import KnowledgeExploreView from './KnowledgeExploreView.vue'

// M5 Step 3：页面新增 useRoute()，测试用可变 query 驱动（默认空 → 既有行为不变）。
const { routeQuery } = vi.hoisted(() => ({ routeQuery: { value: {} as Record<string, unknown> } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: routeQuery.value }) }))

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: {
    list: vi.fn(),
    questions: vi.fn(),
  },
}))

vi.mock('@/api/mastery', () => ({
  masteryApi: {
    get: vi.fn(),
  },
  masteryLevel: (score: number) => ({ tone: 'steady', label: '稳步提升' }),
}))

function kp(id: number, name: string, overrides: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject: '数据结构',
    parent_id: null,
    description: null,
    status: 'active',
    source: 'system',
    node_type: 'concept',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
    ...overrides,
  }
}

// 线性表(container) └─ 栈(concept) └─ 顺序栈(concept)
const fixtures: KnowledgePoint[] = [
  kp(1, '线性表', { node_type: 'container' }),
  kp(2, '栈', { parent_id: 1, description: '后进先出的线性结构', difficulty: 'easy' }),
  kp(3, '顺序栈', { parent_id: 2 }),
]

function question(id: number, stem: string): Question {
  return {
    id,
    subject: '数据结构',
    knowledge_point: '栈',
    question_type: 'choice',
    stem,
    options_json: null,
    answer: 'A',
    analysis: null,
    source: 'admin',
    is_favorite: false,
    difficulty: 'easy',
    visibility: 'shared',
  }
}

async function setup() {
  vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: fixtures } as any)
  const wrapper = mount(KnowledgeExploreView)
  await flushPromises()
  return wrapper as VueWrapper<any>
}

function treeButton(wrapper: VueWrapper<any>, name: string) {
  return wrapper.findAll('.tree-btn').find((btn: any) => btn.text().includes(name))
}

describe('KnowledgeExploreView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeQuery.value = {}
    vi.mocked(masteryApi.get).mockRejectedValue({ response: { status: 404 } })
    vi.mocked(knowledgePointsApi.questions).mockResolvedValue({ data: [] } as any)
  })

  it('渲染学科知识树（container 与 concept 均可见）', async () => {
    const wrapper = await setup()
    const names = wrapper.findAll('.tree-btn').map((btn: any) => btn.text())
    expect(names.some((text: string) => text.includes('线性表'))).toBe(true)
    expect(names.some((text: string) => text.includes('栈'))).toBe(true)
    expect(names.some((text: string) => text.includes('顺序栈'))).toBe(true)
  })

  it('点击 concept 显示详情、掌握度与关联题目', async () => {
    vi.mocked(masteryApi.get).mockResolvedValue({
      data: {
        id: 1,
        knowledge_point_id: 2,
        mastery_score: 72,
        attempt_count: 5,
        correct_count: 4,
        correct_streak: 2,
        last_answered_at: null,
        last_correct_at: null,
        last_reviewed_at: null,
        created_at: '2026-10-01T00:00:00',
        updated_at: '2026-10-01T00:00:00',
        knowledge_point: null,
      },
    } as any)
    vi.mocked(knowledgePointsApi.questions).mockResolvedValue({
      data: [question(101, '栈的特点是什么？')],
    } as any)

    const wrapper = await setup()
    await treeButton(wrapper, '栈')!.trigger('click')
    await flushPromises()

    // 详情面板：名称、描述、掌握度、题目
    expect(wrapper.text()).toContain('后进先出的线性结构')
    expect(wrapper.text()).toContain('72%')
    expect(wrapper.text()).toContain('栈的特点是什么？')
    expect(knowledgePointsApi.questions).toHaveBeenCalledWith(2)
    expect(masteryApi.get).toHaveBeenCalledWith(2)
  })

  it('点击 container 不会进入详情（container 永不可练习）', async () => {
    const wrapper = await setup()
    await treeButton(wrapper, '线性表')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('在左侧选择一个知识点')
    expect(knowledgePointsApi.questions).not.toHaveBeenCalled()
  })

  it('折叠 container 后其后代隐藏', async () => {
    const wrapper = await setup()
    await treeButton(wrapper, '线性表')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('顺序栈')
  })

  it('未作答过的知识点掌握度按空态处理（不报错）', async () => {
    const wrapper = await setup()
    await treeButton(wrapper, '栈')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('暂无掌握度记录')
  })

  // ------------------------------------------- M5 Step 3：消费 ?knowledge_point_id
  it('带 ?knowledge_point_id 进入时自动定位选中该 concept 并加载详情', async () => {
    routeQuery.value = { knowledge_point_id: '3' }
    const wrapper = await setup()

    // 自动选中「顺序栈」→ 详情面板加载（无需手动点击树节点）
    expect(wrapper.find('.tree-item.is-selected').text()).toContain('顺序栈')
    expect(knowledgePointsApi.questions).toHaveBeenCalledWith(3)
    expect(masteryApi.get).toHaveBeenCalledWith(3)
  })

  it('?knowledge_point_id 指向 container 或非法值时静默忽略（保持默认空态）', async () => {
    routeQuery.value = { knowledge_point_id: '1' }
    const wrapper = await setup()
    expect(wrapper.find('.tree-item.is-selected').exists()).toBe(false)
    expect(knowledgePointsApi.questions).not.toHaveBeenCalled()

    routeQuery.value = { knowledge_point_id: 'abc' }
    const another = await setup()
    expect(another.find('.tree-item.is-selected').exists()).toBe(false)
    expect(knowledgePointsApi.questions).not.toHaveBeenCalled()
  })
})
