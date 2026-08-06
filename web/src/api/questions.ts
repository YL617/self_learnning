import { http } from './http'
import type { AnswerRecord, Question, WrongBookItem } from '@/types'

export interface QuestionGeneratePayload {
  subject: string
  knowledge_point: string
  count: number
  question_type: 'choice' | 'fill' | 'short_answer'
  document_id?: number
}

export const questionsApi = {
  list: () => http.get<Question[]>('/questions'),
  generate: (data: QuestionGeneratePayload) =>
    http.post<Question[]>('/questions/generate', data),
  setFavorite: (questionId: number, isFavorite: boolean) =>
    http.patch<Question>(`/questions/${questionId}/favorite`, {
      is_favorite: isFavorite,
    }),
  remove: (questionId: number) => http.delete<void>(`/questions/${questionId}`),
  submitAnswer: (questionId: number, userAnswer: string) =>
    http.post<AnswerRecord>(`/questions/${questionId}/answers`, { user_answer: userAnswer }),
  wrongBook: () => http.get<WrongBookItem[]>('/wrong-book'),
  updateWrongItem: (itemId: number, mastered: boolean) =>
    http.patch<WrongBookItem>(`/wrong-book/${itemId}`, { mastered }),
}
