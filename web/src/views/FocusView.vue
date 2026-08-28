<script setup lang="ts">
import {
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Play,
  Plus,
  Square,
  Timer,
  Trash2,
  X,
} from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

import { focusApi } from '@/api/focus'
import type { FocusSession, FocusStats, FocusTag } from '@/types'
import { petEvents } from '@/utils/petEvents'

const TAG_COLORS = [
  '#0f766e',
  '#2563eb',
  '#7c3aed',
  '#0891b2',
  '#16a34a',
  '#b45309',
  '#ea580c',
  '#dc2626',
]
const DEFAULT_COLOR = TAG_COLORS[0]

const stats = ref<FocusStats>({ total_minutes: 0, session_count: 0, today_minutes: 0 })
const tags = ref<FocusTag[]>([])
const selectedTagId = ref<number | null>(null)
const addingTag = ref(false)
const newTagName = ref('')
const newTagColor = ref(DEFAULT_COLOR)
const editingTagId = ref<number | null>(null)
const editTagName = ref('')
const editTagColor = ref(DEFAULT_COLOR)
const duration = ref(25)
const activeSession = ref<FocusSession | null>(null)
const remainingSeconds = ref(0)
const timerHandle = ref<number | null>(null)
const nowHandle = ref<number | null>(null)
const error = ref('')
const lastActivity = ref(Date.now())
const activeVerified = ref(true)
const sessions = ref<FocusSession[]>([])
const timelineLoading = ref(false)
const timelineDay = ref(localDateKey(new Date()))
const now = ref(new Date())
const showLeaveConfirm = ref(false)
let leaveResolver: ((confirmed: boolean) => void) | null = null

const selectedTag = computed(
  () => tags.value.find((tag) => tag.id === selectedTagId.value) || null,
)

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function localDateKey(value: Date): string {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function todayKey(): string {
  return localDateKey(new Date())
}

function formatTime(value: Date): string {
  return `${pad(value.getHours())}:${pad(value.getMinutes())}`
}

function addDaysToKey(key: string, delta: number): string {
  const [year, month, day] = key.split('-').map(Number)
  return localDateKey(new Date(year, month - 1, day + delta))
}

function parseUtc(value: string): Date {
  if (value.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value)
  }
  return new Date(`${value}Z`)
}

const displayTime = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60)
  const seconds = remainingSeconds.value % 60
  return `${pad(minutes)}:${pad(seconds)}`
})

async function loadStats() {
  try {
    const { data } = await focusApi.stats()
    stats.value = data
  } catch {
    stats.value = { total_minutes: 0, session_count: 0, today_minutes: 0 }
  }
}

async function loadTags() {
  try {
    const { data } = await focusApi.tags()
    tags.value = data
    if (!selectedTagId.value || !data.some((tag) => tag.id === selectedTagId.value)) {
      selectedTagId.value = data[0]?.id ?? null
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '标签加载失败'
  }
}

async function loadSessions() {
  timelineLoading.value = true
  try {
    const { data } = await focusApi.sessions(30)
    sessions.value = data
  } catch {
    sessions.value = []
  } finally {
    timelineLoading.value = false
  }
}

async function saveTag() {
  const name = newTagName.value.trim()
  if (!name) {
    error.value = '请输入标签名称'
    return
  }
  error.value = ''
  try {
    const { data } = await focusApi.createTag(name, newTagColor.value)
    tags.value.push(data)
    selectedTagId.value = data.id
    newTagName.value = ''
    newTagColor.value = DEFAULT_COLOR
    addingTag.value = false
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '添加失败'
  }
}

function cancelAdd() {
  addingTag.value = false
  newTagName.value = ''
  newTagColor.value = DEFAULT_COLOR
}

function startEdit(tag: FocusTag) {
  editingTagId.value = tag.id
  editTagName.value = tag.name
  editTagColor.value = tag.color
}

function cancelEdit() {
  editingTagId.value = null
  editTagName.value = ''
  editTagColor.value = DEFAULT_COLOR
}

async function saveEdit() {
  if (editingTagId.value === null) return
  const name = editTagName.value.trim()
  if (!name) {
    error.value = '请输入标签名称'
    return
  }
  error.value = ''
  try {
    const { data } = await focusApi.updateTag(editingTagId.value, {
      name,
      color: editTagColor.value,
    })
    const index = tags.value.findIndex((tag) => tag.id === data.id)
    if (index >= 0) tags.value[index] = data
    cancelEdit()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '保存失败'
  }
}

async function removeTag(tag: FocusTag) {
  if (!window.confirm(`确定删除标签「${tag.name}」吗？历史专注记录会保留。`)) return
  error.value = ''
  try {
    await focusApi.removeTag(tag.id)
    tags.value = tags.value.filter((item) => item.id !== tag.id)
    if (selectedTagId.value === tag.id) {
      selectedTagId.value = tags.value[0]?.id ?? null
    }
    if (editingTagId.value === tag.id) cancelEdit()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

async function start() {
  if (!selectedTag.value) return
  error.value = ''
  try {
    const { data } = await focusApi.startSession(
      selectedTag.value.name,
      duration.value,
      selectedTag.value.color,
    )
    activeSession.value = data
    remainingSeconds.value = data.duration_minutes * 60
    lastActivity.value = Date.now()
    activeVerified.value = true
    if (!sessions.value.some((session) => session.id === data.id)) {
      sessions.value.push(data)
    }
    window.addEventListener('mousemove', markActivity)
    window.addEventListener('keydown', markActivity)
    timerHandle.value = window.setInterval(() => {
      remainingSeconds.value -= 1
      if (Date.now() - lastActivity.value > 5 * 60 * 1000) {
        activeVerified.value = false
      }
      if (remainingSeconds.value <= 0) void complete()
    }, 1000)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '开始失败'
  }
}

function markActivity() {
  lastActivity.value = Date.now()
}

async function complete() {
  if (timerHandle.value !== null) {
    window.clearInterval(timerHandle.value)
    timerHandle.value = null
  }
  if (!activeSession.value) return
  const session = activeSession.value
  activeSession.value = null
  showLeaveConfirm.value = false
  leaveResolver?.(false)
  leaveResolver = null
  window.removeEventListener('mousemove', markActivity)
  window.removeEventListener('keydown', markActivity)
  try {
    await focusApi.completeSession(session.id, activeVerified.value)
    if (activeVerified.value) {
      petEvents.emit({ kind: 'focus' })
    }
    await Promise.all([loadStats(), loadSessions()])
    if (!activeVerified.value) {
      error.value = '检测到长时间无操作，本次专注未计入金币与经验'
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '记录失败'
  }
}

function stopTimer() {
  if (timerHandle.value !== null) {
    window.clearInterval(timerHandle.value)
    timerHandle.value = null
  }
}

function confirmLeaveAction() {
  showLeaveConfirm.value = false
  leaveResolver?.(true)
  leaveResolver = null
}

function cancelLeaveAction() {
  showLeaveConfirm.value = false
  leaveResolver?.(false)
  leaveResolver = null
}

onBeforeRouteLeave(async () => {
  if (!activeSession.value) return true
  showLeaveConfirm.value = true
  const confirmed = await new Promise<boolean>((resolve) => {
    leaveResolver = resolve
  })
  if (!confirmed) return false
  const session = activeSession.value
  activeSession.value = null
  stopTimer()
  try {
    await focusApi.completeSession(session.id, false)
    await Promise.all([loadStats(), loadSessions()])
  } catch {
    // 离开时即使记录失败也放行导航
  }
  return true
})

const hourTicks = Array.from({ length: 25 }, (_, index) => index)
const isToday = computed(() => timelineDay.value === todayKey())
const canNext = computed(() => timelineDay.value < todayKey())

const visibleSessions = computed(() =>
  [...sessions.value]
    .filter((session) => {
      const start = parseUtc(session.started_at)
      if (localDateKey(start) !== timelineDay.value) return false
      if (!session.completed && !isToday.value) return false
      return true
    })
    .sort(
      (a, b) => parseUtc(a.started_at).getTime() - parseUtc(b.started_at).getTime(),
    ),
)

function minutesOfDay(value: Date): number {
  return value.getHours() * 60 + value.getMinutes() + value.getSeconds() / 60
}

function clampMinute(value: number): number {
  return Math.min(1440, Math.max(0, value))
}

function sessionEnd(session: FocusSession): Date {
  return session.ended_at ? parseUtc(session.ended_at) : now.value
}

function blockStyle(session: FocusSession): Record<string, string> {
  const startMinute = clampMinute(minutesOfDay(parseUtc(session.started_at)))
  let endMinute = clampMinute(minutesOfDay(sessionEnd(session)))
  if (endMinute < startMinute) endMinute = 1440
  return {
    top: `${(startMinute / 1440) * 100}%`,
    height: `${Math.max(((endMinute - startMinute) / 1440) * 100, 0.25)}%`,
  }
}

const nowTop = computed(
  () => `${(clampMinute(minutesOfDay(now.value)) / 1440) * 100}%`,
)

function sessionColor(session: FocusSession): string {
  return session.tag_color || DEFAULT_COLOR
}

function sessionTimeRange(session: FocusSession): string {
  const start = parseUtc(session.started_at)
  return `${formatTime(start)} - ${formatTime(sessionEnd(session))}`
}

function sessionDurationText(session: FocusSession): string {
  const start = parseUtc(session.started_at)
  const minutes = Math.max(
    0,
    Math.round((sessionEnd(session).getTime() - start.getTime()) / 60000),
  )
  if (minutes < 60) return `${minutes} 分钟`
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟`
}

function sessionTitle(session: FocusSession): string {
  return `${session.task_label} · ${sessionTimeRange(session)} · ${sessionDurationText(session)}`
}

function goToday() {
  timelineDay.value = todayKey()
}

function prevDay() {
  timelineDay.value = addDaysToKey(timelineDay.value, -1)
}

function nextDay() {
  if (!canNext.value) return
  timelineDay.value = addDaysToKey(timelineDay.value, 1)
}

const timelineTitle = computed(() => {
  const [year, month, day] = timelineDay.value.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  const week = ['日', '一', '二', '三', '四', '五', '六'][date.getDay()]
  return `${year}年${month}月${day}日 星期${week}`
})

onMounted(async () => {
  nowHandle.value = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
  await Promise.all([loadStats(), loadTags(), loadSessions()])
})

onBeforeUnmount(() => {
  if (nowHandle.value !== null) window.clearInterval(nowHandle.value)
  if (timerHandle.value !== null) window.clearInterval(timerHandle.value)
  window.removeEventListener('mousemove', markActivity)
  window.removeEventListener('keydown', markActivity)
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">专注模式</h1>
        <p class="page-subtitle">番茄钟专注学习，完成后获得智学币与宠物经验</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <div class="grid grid-3">
      <div class="card" style="grid-column: span 2">
        <h2><Timer :size="16" /> 番茄钟</h2>
        <template v-if="!activeSession">
          <div class="form-grid">
            <div class="field">
              <span>专注任务</span>
              <div class="tag-picker">
                <button
                  v-for="tag in tags"
                  :key="tag.id"
                  class="tag-chip"
                  :class="{ selected: selectedTagId === tag.id }"
                  type="button"
                  @click="selectedTagId = tag.id"
                >
                  <span class="tag-dot" :style="{ background: tag.color }" />
                  <span>{{ tag.name }}</span>
                  <span class="tag-actions">
                    <Pencil :size="12" @click.stop="startEdit(tag)" />
                    <Trash2 :size="12" @click.stop="removeTag(tag)" />
                  </span>
                </button>
                <button
                  class="tag-chip tag-chip-add"
                  type="button"
                  @click="addingTag = !addingTag"
                >
                  <Plus :size="14" />
                  添加
                </button>
              </div>
              <div v-if="addingTag" class="tag-form">
                <input
                  v-model="newTagName"
                  class="input"
                  maxlength="40"
                  placeholder="标签名称，如：数学复习"
                />
                <div class="color-swatches">
                  <button
                    v-for="color in TAG_COLORS"
                    :key="color"
                    class="color-swatch"
                    :class="{ active: newTagColor === color }"
                    type="button"
                    :style="{ background: color }"
                    @click="newTagColor = color"
                  />
                </div>
                <div class="row gap">
                  <button class="btn btn-primary btn-sm" type="button" @click="saveTag">
                    <Check :size="15" />
                    确定
                  </button>
                  <button class="btn btn-ghost btn-sm" type="button" @click="cancelAdd">
                    <X :size="15" />
                    取消
                  </button>
                </div>
              </div>
              <div v-if="editingTagId" class="tag-form">
                <input v-model="editTagName" class="input" maxlength="40" />
                <div class="color-swatches">
                  <button
                    v-for="color in TAG_COLORS"
                    :key="color"
                    class="color-swatch"
                    :class="{ active: editTagColor === color }"
                    type="button"
                    :style="{ background: color }"
                    @click="editTagColor = color"
                  />
                </div>
                <div class="row gap">
                  <button class="btn btn-primary btn-sm" type="button" @click="saveEdit">
                    <Check :size="15" />
                    保存
                  </button>
                  <button class="btn btn-ghost btn-sm" type="button" @click="cancelEdit">
                    <X :size="15" />
                    取消
                  </button>
                </div>
              </div>
              <p v-if="!tags.length && !addingTag" class="muted tag-hint">
                还没有任务标签，点击“添加”创建一个
              </p>
            </div>
            <div class="field">
              <span>时长（分钟）</span>
              <select v-model.number="duration" class="select">
                <option :value="25">25 分钟</option>
                <option :value="45">45 分钟</option>
                <option :value="60">60 分钟</option>
                <option :value="90">90 分钟</option>
              </select>
            </div>
          </div>
          <button
            class="btn btn-primary"
            style="margin-top: 14px"
            type="button"
            :disabled="!selectedTag"
            @click="start"
          >
            <Play :size="16" />
            开始专注
          </button>
          <p v-if="!selectedTag" class="muted tag-hint">
            请先添加并选择一个专注任务
          </p>
        </template>
        <template v-else>
          <div class="timer-display">{{ displayTime }}</div>
          <p style="text-align: center" class="muted">{{ activeSession.task_label }}</p>
          <p v-if="!activeVerified" class="text-danger" style="text-align: center">
            检测到长时间无操作，本次不会获得金币与经验
          </p>
          <button class="btn btn-danger btn-block" type="button" @click="complete">
            <Square :size="16" />
            完成并记录
          </button>
        </template>
      </div>

      <div class="card">
        <h2>专注统计</h2>
        <div class="grid gap" style="gap: 14px">
          <div class="stat-card">
            <div class="stat-icon"><Timer :size="20" /></div>
            <div>
              <div class="stat-value">{{ stats.today_minutes }}</div>
              <div class="stat-label">今日专注（分钟）</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon"><Timer :size="20" /></div>
            <div>
              <div class="stat-value">{{ stats.total_minutes }}</div>
              <div class="stat-label">累计专注（分钟）</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon"><Timer :size="20" /></div>
            <div>
              <div class="stat-value">{{ stats.session_count }}</div>
              <div class="stat-label">完成番茄钟</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card timeline-card">
      <div class="timeline-head">
        <h2><CalendarDays :size="16" /> 专注时间轴</h2>
        <div class="timeline-nav">
          <button class="icon-btn" type="button" title="前一天" @click="prevDay">
            <ChevronLeft :size="17" />
          </button>
          <span class="timeline-day-label">{{ timelineTitle }}</span>
          <button class="icon-btn" type="button" title="后一天" :disabled="!canNext" @click="nextDay">
            <ChevronRight :size="17" />
          </button>
          <button class="btn btn-outline today-btn" type="button" @click="goToday">
            今天
          </button>
        </div>
      </div>

      <div class="timeline-wrap">
        <div class="timeline-axis">
          <div class="timeline-scale">
            <div
              v-for="hour in hourTicks"
              :key="hour"
              class="timeline-tick"
              :style="{ top: (hour / 24) * 100 + '%' }"
            >
              <span>{{ String(hour).padStart(2, '0') }}:00</span>
            </div>
          </div>
        </div>
        <div class="timeline-track">
          <div class="timeline-scale">
            <div
              v-for="hour in hourTicks"
              :key="`line-${hour}`"
              class="hour-line"
              :style="{ top: (hour / 24) * 100 + '%' }"
            />
            <div v-if="isToday" class="now-line" :style="{ top: nowTop }">
              <span class="now-dot" />
              <span class="now-label">现在 {{ formatTime(now) }}</span>
            </div>
            <div
              v-for="session in visibleSessions"
              :key="session.id"
              class="focus-block"
              :class="{ active: !session.completed }"
              :style="blockStyle(session)"
              :title="sessionTitle(session)"
            >
              <span class="focus-block-bar" :style="{ background: sessionColor(session) }" />
            </div>
            <div v-if="timelineLoading" class="timeline-empty">正在加载...</div>
            <div v-else-if="!visibleSessions.length" class="timeline-empty">
              这一天没有专注记录
            </div>
          </div>
        </div>
      </div>

      <div v-if="visibleSessions.length" class="timeline-list">
        <h3>记录明细</h3>
        <div
          v-for="session in visibleSessions"
          :key="`list-${session.id}`"
          class="timeline-list-item"
        >
          <span class="timeline-list-dot" :style="{ background: sessionColor(session) }" />
          <div class="list-item-main">
            <div class="list-item-title">
              {{ session.task_label }}
              <span v-if="!session.completed" class="badge badge-teal">进行中</span>
            </div>
            <div class="list-item-sub">
              {{ sessionTimeRange(session) }} · {{ sessionDurationText(session) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showLeaveConfirm" class="confirm-overlay">
      <div class="confirm-dialog">
        <h3>专注还未结束</h3>
        <p>
          当前正在「{{ activeSession?.task_label }}」。离开后本次专注会被中断，
          不计入金币与经验。
        </p>
        <div class="confirm-actions">
          <button class="btn btn-ghost" type="button" @click="cancelLeaveAction">
            继续专注
          </button>
          <button class="btn btn-danger" type="button" @click="confirmLeaveAction">
            结束并离开
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.btn-sm {
  padding: 6px 10px;
  font-size: 12.5px;
}

.tag-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text-2);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.tag-chip:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.tag-chip.selected {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
}

.tag-chip-add {
  border-style: dashed;
  color: var(--primary);
}

.tag-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-actions {
  display: inline-flex;
  gap: 5px;
  margin-left: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.tag-chip:hover .tag-actions {
  opacity: 0.75;
}

.tag-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.color-swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.color-swatch {
  width: 26px;
  height: 26px;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease;
}

.color-swatch:hover {
  transform: scale(1.12);
}

.color-swatch.active {
  border-color: var(--text);
  box-shadow: 0 0 0 2px var(--surface);
}

.tag-hint {
  margin-top: 6px;
  font-size: 12px;
}

.timeline-card {
  width: 100%;
}

.timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.timeline-head h2 {
  margin: 0;
}

.timeline-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-day-label {
  min-width: 158px;
  text-align: center;
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
}

.today-btn {
  padding: 5px 11px;
  font-size: 13px;
}

.timeline-wrap {
  --timeline-height: 1184px;
  display: flex;
  gap: 10px;
  height: 500px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
}

.timeline-axis {
  position: relative;
  width: 58px;
  flex-shrink: 0;
  height: var(--timeline-height);
  border-right: 1px solid var(--border);
}

.timeline-tick {
  position: absolute;
  right: 8px;
  transform: translateY(-50%);
  color: var(--text-3);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.timeline-track {
  position: relative;
  flex: 1;
  min-width: 0;
  height: var(--timeline-height);
}

.timeline-scale {
  position: relative;
  height: calc(var(--timeline-height) - 32px);
  margin-top: 16px;
}

.hour-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px solid var(--border);
  opacity: 0.75;
}

.now-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 2px solid var(--danger);
  z-index: 5;
  pointer-events: none;
}

.now-dot {
  position: absolute;
  left: -4px;
  top: -5px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--danger);
  box-shadow: 0 0 0 3px rgba(194, 65, 43, 0.15);
}

.now-label {
  position: absolute;
  left: 8px;
  top: 6px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface);
  color: var(--danger);
  font-size: 11px;
  font-weight: 700;
}

.focus-block {
  position: absolute;
  left: 0;
  right: 0;
  z-index: 4;
}

.focus-block-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  border-radius: 0 4px 4px 0;
  opacity: 0.88;
  transition: opacity 0.15s ease, box-shadow 0.15s ease;
}

.focus-block:hover .focus-block-bar {
  opacity: 1;
  box-shadow: 0 0 0 1px var(--border-strong);
}

.focus-block.active .focus-block-bar {
  opacity: 1;
  box-shadow: 0 0 10px rgba(15, 118, 110, 0.45);
}

.timeline-empty {
  position: absolute;
  top: 120px;
  left: 0;
  right: 0;
  height: 80px;
  display: grid;
  place-items: center;
  color: var(--text-3);
  font-size: 13px;
  z-index: 2;
  pointer-events: none;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
}

.timeline-list h3 {
  margin: 0 0 2px;
  color: var(--text-2);
  font-size: 13px;
}

.timeline-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.timeline-list-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(24, 24, 22, 0.42);
  backdrop-filter: blur(2px);
}

.confirm-dialog {
  width: 100%;
  max-width: 400px;
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
}

.confirm-dialog h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 700;
}

.confirm-dialog p {
  margin: 0 0 18px;
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.7;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 700px) {
  .timeline-wrap {
    height: 440px;
  }

  .timeline-day-label {
    min-width: 0;
  }
}
</style>
