import { http } from './http'
import type { KnowledgePointMastery, MasterySummary } from '@/types'

export interface MasteryListParams {
  limit?: number
}

export interface WeakMasteryParams {
  threshold?: number
  limit?: number
}

// 大阶段 2：掌握度由答题事务内的后端算法维护，前端只读。
export const masteryApi = {
  list: (params?: MasteryListParams) =>
    http.get<KnowledgePointMastery[]>('/mastery', { params }),
  summary: () => http.get<MasterySummary>('/mastery/summary'),
  weak: (params?: WeakMasteryParams) =>
    http.get<KnowledgePointMastery[]>('/mastery/weak', { params }),
  // 未产生过掌握度记录时后端返回 404，调用方按"暂无记录"处理。
  get: (knowledgePointId: number) =>
    http.get<KnowledgePointMastery>(`/mastery/${knowledgePointId}`),
}

export type MasteryTone = 'weak' | 'steady' | 'strong'

export interface MasteryLevel {
  tone: MasteryTone
  label: string
}

const LEVELS: { min: number; level: MasteryLevel }[] = [
  { min: 85, level: { tone: 'strong', label: '掌握良好' } },
  { min: 60, level: { tone: 'steady', label: '稳步提升' } },
  { min: 0, level: { tone: 'weak', label: '需要加强' } },
]

/** 把 0~100 的掌握度映射成可展示的等级（纯函数，便于测试）。 */
export function masteryLevel(score: number): MasteryLevel {
  const bounded = Math.max(0, Math.min(100, Math.round(score)))
  return LEVELS.find((entry) => bounded >= entry.min)!.level
}
