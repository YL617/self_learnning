import { http } from './http'
import type { CoinTransaction, FocusSession, FocusStats, Pet } from '@/types'

export const focusApi = {
  startSession: (taskLabel: string, durationMinutes: number) =>
    http.post<FocusSession>('/focus/sessions', {
      task_label: taskLabel,
      duration_minutes: durationMinutes,
    }),
  completeSession: (sessionId: number) =>
    http.patch<FocusSession>(`/focus/sessions/${sessionId}/complete`),
  stats: () => http.get<FocusStats>('/focus/stats'),
  pet: () => http.get<Pet>('/pets'),
  renamePet: (petId: number, name: string) =>
    http.patch<Pet>(`/pets/${petId}`, { name }),
  feedPet: (petId: number, amount: number) =>
    http.post<Pet>(`/pets/${petId}/feed`, { amount }),
  transactions: () => http.get<CoinTransaction[]>('/coins/transactions'),
}
