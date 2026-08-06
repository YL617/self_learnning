import { http } from './http'
import type { PlanItem, PlanGenerateRequest, StudyPlan, StudyPlanCreate } from '@/types'

export const plansApi = {
  list: () => http.get<StudyPlan[]>('/plans'),
  get: (id: number) => http.get<StudyPlan>(`/plans/${id}`),
  create: (data: StudyPlanCreate) => http.post<StudyPlan>('/plans', data),
  generate: (data: PlanGenerateRequest) => http.post<StudyPlan>('/plans/generate', data),
  adjust: (id: number) => http.post<StudyPlan>(`/plans/${id}/adjust`),
  completeItem: (itemId: number, completed: boolean) =>
    http.patch<PlanItem>(`/plans/items/${itemId}`, { completed }),
  remove: (id: number) => http.delete<void>(`/plans/${id}`),
  removeItem: (itemId: number) => http.delete<void>(`/plans/items/${itemId}`),
}
