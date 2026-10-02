import { describe, expect, it } from 'vitest'

import type { KnowledgePoint } from '@/types'
import { buildRows, computeDepths, parentCandidates, statusLabel } from './knowledgePoints'

function kp(
  id: number,
  name: string,
  overrides: Partial<KnowledgePoint> = {},
): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject: '数据结构',
    parent_id: null,
    description: null,
    status: 'active',
    source: 'admin',
    node_type: 'concept',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
    ...overrides,
  }
}

describe('computeDepths', () => {
  it('按 parent_id 推导层级深度', () => {
    const items = [kp(1, '线性表'), kp(2, '栈', { parent_id: 1 }), kp(3, '顺序栈', { parent_id: 2 })]
    expect(computeDepths(items)).toEqual({ 1: 0, 2: 1, 3: 2 })
  })

  it('父级缺失或形成环时不会死循环', () => {
    const items = [kp(1, 'A', { parent_id: 99 }), kp(2, 'B', { parent_id: 3 }), kp(3, 'C', { parent_id: 2 })]
    expect(() => computeDepths(items)).not.toThrow()
    expect(computeDepths(items)[1]).toBe(0)
  })
})

describe('buildRows', () => {
  const items = [
    kp(1, '线性表'),
    kp(2, '栈', { parent_id: 1 }),
    kp(3, '队列', { parent_id: 1, status: 'pending' }),
    kp(4, '进程', { subject: '操作系统', source: 'system' }),
  ]

  it('返回全部行并带父级名称', () => {
    const rows = buildRows(items)
    expect(rows).toHaveLength(4)
    const stack = rows.find((row) => row.id === 2)!
    expect(stack.parentName).toBe('线性表')
    expect(stack.depth).toBe(1)
  })

  it('同一学科内父级先于子级，且同学科行连续', () => {
    const rows = buildRows(items)
    expect(rows.filter((row) => row.subject === '数据结构').map((row) => row.id)).toEqual([
      1, 2, 3,
    ])
    const subjects = rows.map((row) => row.subject)
    const start = subjects.indexOf('数据结构')
    expect(subjects.slice(start, start + 3)).toEqual(['数据结构', '数据结构', '数据结构'])
  })

  it('subject 筛选只保留同学科', () => {
    const rows = buildRows(items, { subject: '操作系统' })
    expect(rows.map((row) => row.id)).toEqual([4])
  })

  it('名称搜索忽略大小写', () => {
    const rows = buildRows([kp(1, 'Stack'), kp(2, 'Queue')], { query: 'stack' })
    expect(rows.map((row) => row.id)).toEqual([1])
  })

  it('无匹配时返回空数组', () => {
    expect(buildRows(items, { query: '不存在的知识点' })).toEqual([])
  })

  // P0：目录 / 知识点本地筛选。
  it('nodeType 筛选只保留对应类型', () => {
    const mixed = [
      kp(1, '数据结构目录', { node_type: 'container' }),
      kp(2, '栈', { node_type: 'concept' }),
      kp(3, '队列', { node_type: 'concept' }),
    ]
    expect(buildRows(mixed, { nodeType: 'container' }).map((row) => row.id)).toEqual([1])
    expect(buildRows(mixed, { nodeType: 'concept' }).map((row) => row.id)).toEqual([2, 3])
    expect(buildRows(mixed, { nodeType: 'all' })).toHaveLength(3)
  })
})

describe('parentCandidates', () => {
  const items = [
    kp(1, '线性表'),
    kp(2, '栈', { parent_id: 1 }),
    kp(3, '顺序栈', { parent_id: 2 }),
    kp(4, '进程', { subject: '操作系统' }),
  ]

  it('只返回同学科知识点', () => {
    const ids = parentCandidates(items, '数据结构', null).map((item) => item.id)
    expect(ids).toEqual([1, 2, 3])
  })

  it('跨学科时不返回任何候选', () => {
    expect(parentCandidates(items, '操作系统', null).map((i) => i.id)).toEqual([4])
  })

  it('编辑时排除自身与后代，避免形成环', () => {
    const ids = parentCandidates(items, '数据结构', 2).map((item) => item.id)
    expect(ids).toEqual([1])
  })

  it('学科为空时返回空数组', () => {
    expect(parentCandidates(items, '   ', null)).toEqual([])
  })

  // P0：container 只能挂在 container 之下；concept 的父级可以是两者之一。
  it('子节点为目录时，父级候选只保留目录节点', () => {
    const mixed = [
      kp(1, '数据结构', { node_type: 'container' }),
      kp(2, '线性表', { node_type: 'container', parent_id: 1 }),
      kp(3, '栈', { node_type: 'concept', parent_id: 2 }),
    ]
    const containerParents = parentCandidates(mixed, '数据结构', null, 'container').map((i) => i.id)
    expect(containerParents).toEqual([1, 2])

    const conceptParents = parentCandidates(mixed, '数据结构', null, 'concept').map((i) => i.id)
    expect(conceptParents).toEqual([1, 2, 3])
  })
})

describe('statusLabel', () => {
  it('映射为可读中文', () => {
    expect(statusLabel('active')).toBe('启用')
    expect(statusLabel('pending')).toBe('待审核')
    expect(statusLabel('disabled')).toBe('停用')
  })

  it('未知状态原样返回', () => {
    expect(statusLabel('archived')).toBe('archived')
  })
})
