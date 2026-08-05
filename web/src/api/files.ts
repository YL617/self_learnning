import { http } from './http'
import type { DocumentItem, Question } from '@/types'

export const filesApi = {
  list: () => http.get<DocumentItem[]>('/files'),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<DocumentItem>('/files/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  parse: (documentId: number) =>
    http.post<{ document_id: number; chunks: number; message: string }>(
      `/files/${documentId}/parse`,
    ),
  generateQuestions: (
    documentId: number,
    data: { count: number; question_type: 'choice' | 'fill' | 'short_answer' },
  ) => http.post<Question[]>(`/files/${documentId}/questions`, data),
}
