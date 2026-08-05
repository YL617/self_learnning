export interface FocusStats {
  total_minutes: number
  session_count: number
  today_minutes: number
}

export interface PlanItem {
  id: number
  plan_id: number
  title: string
  subject?: string | null
  scheduled_date: string
  duration_minutes: number
  completed: boolean
  order_index: number
}

export interface StudyPlan {
  id: number
  title: string
  goal?: string | null
  start_date: string
  end_date: string
  status: string
  created_at: string
  items: PlanItem[]
}

export interface PlanGenerateRequest {
  major: string
  grade: string
  goal: string
  daily_minutes: number
  weeks: number
  subjects: string[]
}

export interface Question {
  id: number
  subject: string
  knowledge_point: string
  question_type: string
  stem: string
  options_json?: string | null
  answer: string
  analysis?: string | null
  source: string
}

export interface QuestionGeneratePayload {
  subject: string
  knowledge_point: string
  count: number
  question_type: "choice" | "fill" | "short_answer"
  document_id?: number
}

export interface WrongBookItem {
  id: number
  question_id: number
  review_count: number
  mastered: boolean
  created_at: string
  question?: Question | null
}

export interface DocumentItem {
  id: number
  filename: string
  file_type: string
  storage_path: string
  status: string
  chunks_count: number
  created_at: string
}

export interface Pet {
  id: number
  name: string
  level: number
  exp: number
  mood: number
}

export interface CoinTransaction {
  id: number
  amount: number
  reason: string
  created_at: string
}
