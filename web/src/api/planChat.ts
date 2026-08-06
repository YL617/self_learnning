import { http } from './http'
import type {
  PlanChatConfirm,
  PlanChatMessage,
  PlanChatReply,
  PlanChatStart,
  User,
} from '@/types'

export const planChatApi = {
  start: () => http.post<PlanChatStart>('/plans/chat'),
  messages: (sessionId: number) =>
    http.get<PlanChatMessage[]>(`/plans/chat/${sessionId}/messages`),
  send: (sessionId: number, content: string) =>
    http.post<PlanChatReply>(`/plans/chat/${sessionId}/messages`, { content }),
  confirm: (sessionId: number) =>
    http.post<PlanChatConfirm>(`/plans/chat/${sessionId}/confirm`),
  enableDemoVip: () => http.post<User>('/users/me/membership/demo'),
}
