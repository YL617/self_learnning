export interface UserProfile {
  major?: string | null
  grade?: string | null
  goals?: string | null
  daily_study_minutes: number
  weak_subjects?: string | null
  school_level?: string | null
  pain_point?: string | null
  learning_style?: string | null
  weekly_study_minutes: number
  available_time_slots?: string | null
  onboarding_completed: boolean
  onboarding_completed_at?: string | null
}

export interface User {
  id: number
  email: string
  username: string
  membership_level: string
  profile?: UserProfile | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
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

export interface StudyPlanCreate {
  title: string
  goal?: string
  start_date: string
  end_date: string
}

export interface PlanChatMessage {
  id: number
  role: string
  content: string
  created_at: string
}

export interface PlanChatStart {
  session_id: number
  reply: string
  status: string
}

export interface PlanChatReply {
  session_id: number
  reply: string
  status: string
  draft?: PlanDraft | null
}

export interface PlanDraft {
  title: string
  goal?: string | null
  items: PlanItem[]
}

export interface PlanChatConfirm {
  plan_id: number
  message: string
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
  profile: UserProfile
  plan?: StudyPlan | null
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

export interface AnswerRecord {
  id: number
  question_id: number
  user_answer: string
  is_correct: boolean
  created_at: string
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
  size_bytes: number
  temp_cleanup_at?: string | null
  created_at: string
}

export interface FocusSession {
  id: number
  task_label: string
  started_at: string
  ended_at?: string | null
  duration_minutes: number
  completed: boolean
}

export interface FocusStats {
  total_minutes: number
  session_count: number
  today_minutes: number
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
  play_count_today: number
  playing_until?: string | null
  last_fed_at?: string | null
}

export interface PetPlaySession {
  id: number
  status: string
  started_at: string
  ended_at?: string | null
  duration_minutes: number
  coin_cost: number
  mood_gain: number
  exp_gain: number
  hunger_loss: number
  created_at: string
}

export interface PetPlaySummary {
  elapsed_minutes: number
  mood_gain: number
  exp_gain: number
  hunger_loss: number
  coins_spent: number
  message: string
}

export interface PetPlayState {
  session?: PetPlaySession | null
  summary?: PetPlaySummary | null
  pet: Pet
}

export interface PetMessage {
  id: number
  role: string
  kind: string
  content: string
  created_at: string
}

export interface PetChatReply {
  reply: string
  pet: Pet
  messages: PetMessage[]
}

export interface PetInteraction {
  reply: string
  pet: Pet
}

export interface CoinTransaction {
  id: number
  amount: number
  reason: string
  created_at: string
}

export interface Todo {
  id: number
  title: string
  due_date: string
  completed: boolean
}

export interface Reminder {
  id: number
  title: string
  remind_at: string
  triggered: boolean
  dismissed: boolean
}

export interface NotificationItem {
  id: number
  kind: string
  title: string
  remind_at?: string | null
}

export interface CalendarEvent {
  date: string
  title: string
  kind: string
  id: number
  completed: boolean
}

export interface CourseChapter {
  id: number
  title: string
  order_index: number
}

export interface Course {
  id: number
  title: string
  platform: string
  url: string
  description?: string | null
  chapters: CourseChapter[]
}

export interface WeeklyReport {
  start_date: string
  end_date: string
  focus_minutes: number
  sessions: number
  answered: number
  correct: number
  coins_earned: number
  wrong_added: number
}
