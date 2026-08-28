import { http } from './http'
import type {
  CoinTransaction,
  FocusSession,
  FocusStats,
  FocusTag,
  Pet,
  PetChatReply,
  PetInteraction,
  PetMessage,
  PetPlayState,
} from '@/types'

export const focusApi = {
  startSession: (
    taskLabel: string,
    durationMinutes: number,
    tagColor?: string | null,
  ) =>
    http.post<FocusSession>('/focus/sessions', {
      task_label: taskLabel,
      duration_minutes: durationMinutes,
      tag_color: tagColor,
    }),
  completeSession: (sessionId: number, verified = true) =>
    http.patch<FocusSession>(`/focus/sessions/${sessionId}/complete`, { verified }),
  stats: () => http.get<FocusStats>('/focus/stats'),
  sessions: (days = 30) =>
    http.get<FocusSession[]>('/focus/sessions', { params: { days } }),
  tags: () => http.get<FocusTag[]>('/focus/tags'),
  createTag: (name: string, color: string) =>
    http.post<FocusTag>('/focus/tags', { name, color }),
  updateTag: (tagId: number, payload: { name?: string; color?: string }) =>
    http.patch<FocusTag>(`/focus/tags/${tagId}`, payload),
  removeTag: (tagId: number) =>
    http.delete<void>(`/focus/tags/${tagId}`),
  pet: () => http.get<Pet>('/pets'),
  renamePet: (petId: number, name: string) =>
    http.patch<Pet>(`/pets/${petId}`, { name }),
  feedPet: (petId: number, amount: number) =>
    http.post<Pet>(`/pets/${petId}/feed`, { amount }),
  petMessages: (petId: number) =>
    http.get<PetMessage[]>(`/pets/${petId}/messages`),
  greetPet: (petId: number) =>
    http.post<PetChatReply>(`/pets/${petId}/greet`),
  chatPet: (petId: number, message: string) =>
    http.post<PetChatReply>(`/pets/${petId}/chat`, { message }),
  patPet: (petId: number) =>
    http.post<PetInteraction>(`/pets/${petId}/pat`),
  playPet: (petId: number) =>
    http.post<PetInteraction>(`/pets/${petId}/play`),
  revivePet: (petId: number) =>
    http.post<PetInteraction>(`/pets/${petId}/revive`),
  startPetPlay: (petId: number) =>
    http.post<PetPlayState>(`/pets/${petId}/play-out`),
  petPlayState: (petId: number) =>
    http.get<PetPlayState>(`/pets/${petId}/play-session`),
  endPetPlay: (petId: number) =>
    http.post<PetPlayState>(`/pets/${petId}/play-out/end`),
  transactions: () => http.get<CoinTransaction[]>('/coins/transactions'),
}
