import { http } from './http'
import type {
  CoinTransaction,
  FocusSession,
  FocusStats,
  Pet,
  PetChatReply,
  PetInteraction,
  PetMessage,
  PetPlayState,
} from '@/types'

export const focusApi = {
  startSession: (taskLabel: string, durationMinutes: number) =>
    http.post<FocusSession>('/focus/sessions', {
      task_label: taskLabel,
      duration_minutes: durationMinutes,
    }),
  completeSession: (sessionId: number, verified = true) =>
    http.patch<FocusSession>(`/focus/sessions/${sessionId}/complete`, { verified }),
  stats: () => http.get<FocusStats>('/focus/stats'),
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
