import type { KnowledgePoint, KnowledgePointNodeType } from '@/types'
import { NODE_TYPE_ICONS, NODE_TYPE_LABELS } from '@/types'

// 管理页展示行：在知识点基础上补充层级深度与父级名称。
export interface KnowledgePointRow extends KnowledgePoint {
  depth: number
  parentName: string
}

export interface KnowledgePointFilters {
  subject?: string
  query?: string
  // P0：前端本地筛选（服务端另有 node_type 过滤参数）。'all' | 'container' | 'concept'
  nodeType?: KnowledgePointNodeType | 'all'
}

// 后端返回的是扁平列表，这里按 parent_id 推导层级深度（带环保护）。
export function computeDepths(items: KnowledgePoint[]): Record<number, number> {
  const byId = new Map<number, KnowledgePoint>()
  for (const item of items) byId.set(item.id, item)

  const depths: Record<number, number> = {}
  for (const item of items) {
    let depth = 0
    let cursor = item.parent_id ?? null
    const seen = new Set<number>([item.id])
    while (cursor !== null && byId.has(cursor) && !seen.has(cursor) && depth < 100) {
      seen.add(cursor)
      depth += 1
      cursor = byId.get(cursor)!.parent_id ?? null
    }
    depths[item.id] = depth
  }
  return depths
}

// 确定性比较（避免不同 ICU/locale 下中文排序结果不一致）。
function compareText(a: string, b: string): number {
  if (a === b) return 0
  return a < b ? -1 : 1
}

export function buildRows(
  items: KnowledgePoint[],
  filters: KnowledgePointFilters = {},
): KnowledgePointRow[] {
  const subject = (filters.subject || '').trim()
  const needle = (filters.query || '').trim().toLowerCase()
  const nodeType = filters.nodeType || 'all'
  const nameById = new Map<number, string>()
  for (const item of items) nameById.set(item.id, item.name)
  const depths = computeDepths(items)

  return items
    .filter((item) => !subject || item.subject === subject)
    .filter((item) => nodeType === 'all' || item.node_type === nodeType)
    .filter((item) => !needle || item.name.toLowerCase().includes(needle))
    .map((item) => ({
      ...item,
      depth: depths[item.id] ?? 0,
      parentName: item.parent_id != null ? nameById.get(item.parent_id) ?? '' : '',
    }))
    .sort((a, b) => {
      const bySubject = compareText(a.subject, b.subject)
      if (bySubject !== 0) return bySubject
      const byDepth = a.depth - b.depth
      if (byDepth !== 0) return byDepth
      return a.id - b.id
    })
}

// 父级候选：同一学科、排除自己与后代（避免成环）。
// P0：container 只能挂在 container 之下（concept └─ container 结构被后端拒绝）。
export function parentCandidates(
  items: KnowledgePoint[],
  subject: string,
  excludeId: number | null,
  childType: KnowledgePointNodeType = 'concept',
): KnowledgePoint[] {
  const target = subject.trim()
  if (!target) return []
  const childrenByParent = new Map<number, number[]>()
  for (const item of items) {
    if (item.parent_id == null) continue
    const list = childrenByParent.get(item.parent_id) || []
    list.push(item.id)
    childrenByParent.set(item.parent_id, list)
  }
  const blocked = new Set<number>()
  if (excludeId != null) {
    const queue = [excludeId]
    while (queue.length) {
      const current = queue.shift() as number
      if (blocked.has(current)) continue
      blocked.add(current)
      queue.push(...(childrenByParent.get(current) || []))
    }
  }
  return items
    .filter((item) => item.subject === target && !blocked.has(item.id))
    .filter((item) => childType !== 'container' || item.node_type === 'container')
    .sort((a, b) => a.id - b.id)
}

// P0：目录 / 知识点 的展示文案。
export function nodeTypeLabel(nodeType: string): string {
  return nodeType === 'container' ? NODE_TYPE_LABELS.container : NODE_TYPE_LABELS.concept
}

export function nodeTypeIcon(nodeType: string): string {
  return nodeType === 'container' ? NODE_TYPE_ICONS.container : NODE_TYPE_ICONS.concept
}

export const STATUS_LABELS: Record<string, string> = {
  active: '启用',
  pending: '待审核',
  disabled: '停用',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status
}
