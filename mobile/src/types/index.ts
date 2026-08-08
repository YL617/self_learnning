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
  difficulty: string
  suggested_time_slot?: string | null
  buffer_minutes: number
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
  is_favorite: boolean
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
  review_stage: number
  next_review_date?: string | null
  last_reviewed_at?: string | null
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
  hunger: number
  evolution_stage: number
  runaway: boolean
  last_fed_at?: string | null
}

export interface CoinTransaction {
  id: number
  amount: number
  reason: string
  created_at: string
}

export interface OnboardingProfile {
  major?: string | null
  grade?: string | null
  goals?: string | null
  weekly_study_minutes: number
  learning_style?: string | null
  pain_point?: string | null
  school_level?: string | null
  available_time_slots?: string | null
  onboarding_completed: boolean
}

export interface OnboardingPayload {
  major?: string
  grade?: string
  goals: string[]
  weekly_minutes?: number
  learning_style: string[]
  pain_point: string[]
  school_level?: string
  available_time_slots: string[]
  generate_plan: boolean
  complete: boolean
}

export interface OnboardingResponse {
  profile: OnboardingProfile
  plan?: unknown
}
