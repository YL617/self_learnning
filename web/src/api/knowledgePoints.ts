import { http } from './http'
import type { KnowledgePoint, Question } from '@/types'

export interface KnowledgePointListParams {
  subject?: string
  parent_id?: number
  q?: string
}

export interface KnowledgePointPayload {
  name: string
  subject: string
  parent_id?: number | null
  description?: string | null
  status?: 'active' | 'pending' | 'disabled'
  source?: 'system' | 'admin' | 'ai'
}

// Phase 2 结构化知识点：查询与（管理员）写入。
// 普通用户仅使用 list / get / questions；create / update / remove 仅供管理员页面后续接入。
export const knowledgePointsApi = {
  list: (params?: KnowledgePointListParams) =>
    http.get<KnowledgePoint[]>('/knowledge-points', { params }),
  get: (knowledgePointId: number) =>
    http.get<KnowledgePoint>(`/knowledge-points/${knowledgePointId}`),
  questions: (knowledgePointId: number) =>
    http.get<Question[]>(`/knowledge-points/${knowledgePointId}/questions`),
  create: (data: KnowledgePointPayload) =>
    http.post<KnowledgePoint>('/knowledge-points', data),
  update: (knowledgePointId: number, data: Partial<KnowledgePointPayload>) =>
    http.patch<KnowledgePoint>(`/knowledge-points/${knowledgePointId}`, data),
  remove: (knowledgePointId: number) =>
    http.delete<void>(`/knowledge-points/${knowledgePointId}`),
}

// 将知识点列表解析为 id -> name 映射，供关联标签展示使用。
export function toKnowledgePointNameMap(items: KnowledgePoint[]): Record<number, string> {
  const map: Record<number, string> = {}
  for (const item of items) {
    map[item.id] = item.name
  }
  return map
}
