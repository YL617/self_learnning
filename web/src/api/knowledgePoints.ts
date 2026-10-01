import { http } from './http'
import type {
  KnowledgePoint,
  LearningPath,
  PrerequisiteDetail,
  PrerequisiteItem,
  PrerequisiteSuggestResult,
  Question,
} from '@/types'

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

  // 大阶段 3：前置依赖 DAG。
  // 读接口对所有登录用户开放（学生要能看到前置是否满足与学习路径）；
  // 写接口与 LLM 提议仅管理员可用，且 LLM 只提议、不落库。
  prerequisites: (knowledgePointId: number) =>
    http.get<PrerequisiteDetail>(`/knowledge-points/${knowledgePointId}/prerequisites`),
  addPrerequisite: (
    knowledgePointId: number,
    data: { prerequisite_id: number; strength?: number; note?: string | null },
  ) =>
    http.post<PrerequisiteItem>(`/knowledge-points/${knowledgePointId}/prerequisites`, data),
  removePrerequisite: (knowledgePointId: number, prerequisiteId: number) =>
    http.delete<void>(
      `/knowledge-points/${knowledgePointId}/prerequisites/${prerequisiteId}`,
    ),
  learningPath: (knowledgePointId: number) =>
    http.get<LearningPath>(`/knowledge-points/${knowledgePointId}/path`),
  suggestPrerequisites: (knowledgePointId: number) =>
    http.post<PrerequisiteSuggestResult>(
      `/knowledge-points/${knowledgePointId}/prerequisites/suggest`,
    ),
}

// 将知识点列表解析为 id -> name 映射，供关联标签展示使用。
export function toKnowledgePointNameMap(items: KnowledgePoint[]): Record<number, string> {
  const map: Record<number, string> = {}
  for (const item of items) {
    map[item.id] = item.name
  }
  return map
}
