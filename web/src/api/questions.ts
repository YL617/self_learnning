import { http } from './http'
import type { AnswerRecord, Question, QuestionKnowledgePoint, WrongBookItem } from '@/types'

export interface QuestionGeneratePayload {
  subject: string
  knowledge_point: string
  count: number
  question_type: 'choice' | 'fill' | 'short_answer'
  document_id?: number
  reference_question_id?: number
  // Phase 2：可选的结构化知识点；不传时行为与旧版完全一致。
  knowledge_point_id?: number
}

export interface QuestionKnowledgePointAttachPayload {
  knowledge_point_id: number
  role: 'primary' | 'secondary'
}

export interface QuestionKnowledgePointReplacePayload {
  items: QuestionKnowledgePointAttachPayload[]
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
  dueWrongBook: () => http.get<WrongBookItem[]>('/wrong-book/review'),
  updateWrongItem: (itemId: number, mastered: boolean) =>
    http.patch<WrongBookItem>(`/wrong-book/${itemId}`, { mastered }),
  // 完成一次复习：阶段前进、下次复习时间延后（由后端排期规则决定）。
  reviewWrongItem: (itemId: number) =>
    http.patch<WrongBookItem>(`/wrong-book/${itemId}`, { reviewed: true }),

  // ---- Phase 2：题目 ↔ 知识点结构化关联 ----
  getQuestionKnowledgePoints: (questionId: number) =>
    http.get<QuestionKnowledgePoint[]>(`/questions/${questionId}/knowledge-points`),
  attachQuestionKnowledgePoint: (questionId: number, data: QuestionKnowledgePointAttachPayload) =>
    http.post<QuestionKnowledgePoint>(`/questions/${questionId}/knowledge-points`, data),
  replaceQuestionKnowledgePoints: (
    questionId: number,
    data: QuestionKnowledgePointReplacePayload,
  ) => http.put<QuestionKnowledgePoint[]>(`/questions/${questionId}/knowledge-points`, data),
  setPrimaryKnowledgePoint: (questionId: number, knowledgePointId: number) =>
    http.patch<QuestionKnowledgePoint>(
      `/questions/${questionId}/knowledge-points/${knowledgePointId}`,
    ),
  detachQuestionKnowledgePoint: (questionId: number, knowledgePointId: number) =>
    http.delete<void>(`/questions/${questionId}/knowledge-points/${knowledgePointId}`),
}
