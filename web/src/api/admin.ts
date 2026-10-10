import { http } from './http'
import type {
  ActivationCode,
  AdminQuestion,
  AdminQuestionCreatePayload,
  AdminQuestionDetail,
  AdminUser,
  AiMonitorState,
  Course,
  DocumentItem,
  KnowledgeCoverage,
  QuestionKnowledgePoint,
  StatsOverview,
} from '@/types'

export interface CoursePayload {
  title: string
  platform: string
  url: string
  description?: string
  chapters: { title: string; order_index: number }[]
}

export const adminApi = {
  users: (params?: { q?: string; membership_level?: string; role?: string }) =>
    http.get<AdminUser[]>('/admin/users', { params }),
  updateUser: (
    id: number,
    data: { membership_level?: string; role?: string; is_active?: boolean },
  ) => http.patch<AdminUser>(`/admin/users/${id}`, data),
  aiMonitor: () => http.get<AiMonitorState>('/admin/ai-monitor'),
  refreshAiMonitor: () => http.post<AiMonitorState>('/admin/ai-monitor/refresh'),
  stats: () => http.get<StatsOverview>('/admin/stats/overview'),
  activationCodes: () => http.get<ActivationCode[]>('/admin/activation-codes'),
  createActivationCodes: (data: {
    tier: string
    days: number
    count: number
  }) => http.post<ActivationCode[]>('/admin/activation-codes', data),
  revokeActivationCode: (id: number) =>
    http.post<ActivationCode>(`/admin/activation-codes/${id}/revoke`),
  questions: () => http.get<AdminQuestion[]>('/admin/questions'),
  deleteQuestion: (id: number) => http.delete<void>(`/admin/questions/${id}`),
  // M4：管理员题库管理。
  createQuestion: (data: AdminQuestionCreatePayload) =>
    http.post<AdminQuestion>('/admin/questions', data),
  getQuestion: (id: number) =>
    http.get<AdminQuestionDetail>(`/admin/questions/${id}`),
  attachQuestionKnowledgePoint: (
    id: number,
    data: { knowledge_point_id: number; role: 'primary' | 'secondary' },
  ) =>
    http.post<QuestionKnowledgePoint>(`/admin/questions/${id}/knowledge-points`, data),
  knowledgeCoverage: () => http.get<KnowledgeCoverage>('/admin/knowledge-coverage'),
  documents: () => http.get<DocumentItem[]>('/admin/documents'),
  deleteDocument: (id: number) => http.delete<void>(`/admin/documents/${id}`),
  courses: () => http.get<Course[]>('/admin/courses'),
  createCourse: (data: CoursePayload) =>
    http.post<Course>('/admin/courses', data),
  updateCourse: (id: number, data: Partial<CoursePayload>) =>
    http.patch<Course>(`/admin/courses/${id}`, data),
  deleteCourse: (id: number) => http.delete<void>(`/admin/courses/${id}`),
  checkCourseHealth: () =>
    http.post<{ ok: number; bad: number; unknown?: number; checked: number }>(
      '/admin/courses/check-health',
    ),
}
