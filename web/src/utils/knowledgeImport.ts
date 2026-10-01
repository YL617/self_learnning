// 大阶段 4 M3：导入页面的共享文案与格式化。抽出来是为了让
// 「预览表格」「批次面板」两个组件不各写一份词表。

import type {
  KnowledgeImportBlockingReason,
  KnowledgeImportIssue,
  KnowledgeImportPlanCounts,
} from '@/types'

export const ACTION_LABELS: Record<string, string> = {
  create: '新建',
  skip: '跳过',
  update_empty: '补空',
}

export const STATUS_LABELS: Record<string, string> = {
  applied: '已应用',
  failed: '失败',
  rolled_back: '已回滚',
}

export const STRATEGY_LABELS: Record<string, string> = {
  skip: '跳过既有',
  update_empty: '仅补空字段',
}

export const BLOCKING_LABELS: Record<KnowledgeImportBlockingReason, string> = {
  has_children: '仍有子知识点',
  linked_question: '已被题目关联',
  has_mastery: '已有掌握度记录',
  prerequisite_edge: '已进入前置关系图',
}

export function issueText(issue: KnowledgeImportIssue): string {
  return `[${issue.code}] ${issue.message}`
}

export function plannedCount(plan: KnowledgeImportPlanCounts | undefined, key: string): number {
  const value = (plan as Record<string, number | undefined> | undefined)?.[key]
  return value ?? 0
}

export function formatTime(value?: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}
