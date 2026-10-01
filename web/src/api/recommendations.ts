import { http } from './http'
import type { RecommendationToday } from '@/types'

export interface TodayParams {
  limit?: number
}

// 大阶段 3：今日学习建议。
// 由后端确定性规则引擎生成（规则 + 图 + 统计，零训练、零 LLM 数值参与），
// 前端只读展示；建议不写入学习计划（PlanItem）。
export const recommendationsApi = {
  today: (params?: TodayParams) =>
    http.get<RecommendationToday>('/recommendations/today', { params }),
}

export interface ActionTone {
  tone: 'danger' | 'amber' | 'teal' | 'neutral'
  icon: string
}

const ACTION_TONES: Record<string, ActionTone> = {
  review_wrong: { tone: 'danger', icon: '错题' },
  review_weak: { tone: 'amber', icon: '薄弱' },
  learn_new: { tone: 'teal', icon: '新知' },
  practice: { tone: 'neutral', icon: '加练' },
}

/** 把动作类型映射成展示色与短标签（纯函数，便于测试）。 */
export function actionTone(action: string): ActionTone {
  return ACTION_TONES[action] ?? { tone: 'neutral', icon: '建议' }
}
