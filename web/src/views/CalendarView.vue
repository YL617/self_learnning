<script setup lang="ts">
import { CheckCircle2, ChevronLeft, ChevronRight, Circle } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { calendarApi, todosApi } from '@/api/ops'
import { plansApi } from '@/api/plans'
import type { CalendarEvent } from '@/types'
import {
  addDays,
  addMonths,
  dateKey,
  daysInMonth,
  firstOffset,
  isToday,
  monthKey,
} from '@/utils/calendar'

type ViewMode = 'year' | 'month' | 'day'

const view = ref<ViewMode>('month')
const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const selectedDate = ref(
  dateKey(now.getFullYear(), now.getMonth() + 1, now.getDate()),
)
const eventsByMonth = ref<Record<string, CalendarEvent[]>>({})
const error = ref('')
const loading = ref(false)
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

let pendingRequests = 0

const currentMonthKey = computed(() => monthKey(year.value, month.value))
const calendarLabel = computed(() => {
  if (view.value === 'year') return `${year.value}年`
  if (view.value === 'month') return `${year.value}年${month.value}月`
  const [y, m, d] = selectedDate.value.split('-').map(Number)
  const week = ['日', '一', '二', '三', '四', '五', '六'][
    new Date(y, m - 1, d).getDay()
  ]
  return `${y}年${m}月${d}日 星期${week}`
})

async function ensureMonth(key: string) {
  if (eventsByMonth.value[key] !== undefined) return
  pendingRequests += 1
  loading.value = true
  error.value = ''
  try {
    const { data } = await calendarApi.month(key)
    eventsByMonth.value[key] = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '日历数据加载失败'
  } finally {
    pendingRequests -= 1
    if (pendingRequests <= 0) {
      pendingRequests = 0
      loading.value = false
    }
  }
}

async function loadView() {
  if (view.value === 'year') {
    await Promise.all(
      Array.from({ length: 12 }, (_, index) =>
        ensureMonth(monthKey(year.value, index + 1)),
      ),
    )
    return
  }
  const key =
    view.value === 'month'
      ? currentMonthKey.value
      : selectedDate.value.slice(0, 7)
  await ensureMonth(key)
}

function switchView(mode: ViewMode) {
  if (mode === 'day' && selectedDate.value.slice(0, 7) !== currentMonthKey.value) {
    selectedDate.value = dateKey(year.value, month.value, 1)
  }
  view.value = mode
  void loadView()
}

function openMonth(monthNumber: number) {
  month.value = monthNumber
  view.value = 'month'
  void loadView()
}

function openDay(day: number) {
  selectedDate.value = dateKey(year.value, month.value, day)
  view.value = 'day'
  void loadView()
}

function previous() {
  if (view.value === 'year') {
    year.value -= 1
  } else if (view.value === 'month') {
    ;[year.value, month.value] = addMonths(year.value, month.value, -1)
  } else {
    const [y, m, d] = selectedDate.value.split('-').map(Number)
    const next = addDays(y, m, d, -1)
    selectedDate.value = dateKey(next[0], next[1], next[2])
  }
  void loadView()
}

function next() {
  if (view.value === 'year') {
    year.value += 1
  } else if (view.value === 'month') {
    ;[year.value, month.value] = addMonths(year.value, month.value, 1)
  } else {
    const [y, m, d] = selectedDate.value.split('-').map(Number)
    const next = addDays(y, m, d, 1)
    selectedDate.value = dateKey(next[0], next[1], next[2])
  }
  void loadView()
}

function goToday() {
  const today = new Date()
  year.value = today.getFullYear()
  month.value = today.getMonth() + 1
  selectedDate.value = dateKey(
    today.getFullYear(),
    today.getMonth() + 1,
    today.getDate(),
  )
  view.value = 'month'
  void loadView()
}

function eventsForDay(day: number): CalendarEvent[] {
  const key = dateKey(year.value, month.value, day)
  return (
    eventsByMonth.value[currentMonthKey.value]?.filter(
      (event) => event.date === key,
    ) ?? []
  )
}

function dayEvents(): CalendarEvent[] {
  const key = selectedDate.value
  return (
    eventsByMonth.value[key.slice(0, 7)]?.filter(
      (event) => event.date === key,
    ) ?? []
  )
}

function countForMonth(monthNumber: number): number {
  return eventsByMonth.value[monthKey(year.value, monthNumber)]?.length ?? 0
}

function eventDaysForMonth(monthNumber: number): string[] {
  const events = eventsByMonth.value[monthKey(year.value, monthNumber)] ?? []
  return [...new Set(events.map((event) => event.date.slice(8)))]
}

async function toggleEvent(event: CalendarEvent) {
  try {
    if (event.kind === 'todo') {
      await todosApi.update(event.id, !event.completed)
    } else {
      await plansApi.completeItem(event.id, !event.completed)
    }
    const key = event.date.slice(0, 7)
    eventsByMonth.value[key] = []
    await ensureMonth(key)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '更新失败'
  }
}

onMounted(() => {
  void loadView()
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">学习日历</h1>
        <p class="page-subtitle">年 / 月 / 日视图查看计划与待办，点击可标记完成</p>
      </div>
      <div class="calendar-toolbar">
        <div class="segmented">
          <button
            type="button"
            :class="{ active: view === 'year' }"
            @click="switchView('year')"
          >
            年
          </button>
          <button
            type="button"
            :class="{ active: view === 'month' }"
            @click="switchView('month')"
          >
            月
          </button>
          <button
            type="button"
            :class="{ active: view === 'day' }"
            @click="switchView('day')"
          >
            日
          </button>
        </div>
        <div class="nav-buttons">
          <button class="icon-btn" type="button" @click="previous">
            <ChevronLeft :size="18" />
          </button>
          <button class="btn btn-outline today-btn" type="button" @click="goToday">
            今天
          </button>
          <button class="icon-btn" type="button" @click="next">
            <ChevronRight :size="18" />
          </button>
        </div>
        <strong class="calendar-label">{{ calendarLabel }}</strong>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <div v-if="loading" class="empty">正在加载日历数据...</div>

    <div class="card">
      <template v-if="view === 'year'">
        <div class="year-grid">
          <button
            v-for="monthNumber in 12"
            :key="monthNumber"
            class="year-tile"
            type="button"
            @click="openMonth(monthNumber)"
          >
            <span class="year-month-name">{{ monthNumber }}月</span>
            <span class="year-count">{{ countForMonth(monthNumber) }} 个事件</span>
            <span class="year-dots">
              <span
                v-for="day in eventDaysForMonth(monthNumber).slice(0, 10)"
                :key="day"
                class="year-dot"
              />
            </span>
          </button>
        </div>
      </template>

      <template v-else-if="view === 'month'">
        <div class="calendar-grid">
          <div v-for="weekday in weekdays" :key="weekday" class="calendar-weekday">
            {{ weekday }}
          </div>
          <div
            v-for="n in firstOffset(year, month)"
            :key="`empty-${n}`"
            class="calendar-day empty-day"
          />
          <div
            v-for="day in daysInMonth(year, month)"
            :key="day"
            class="calendar-day"
            :class="{ today: isToday(dateKey(year, month, day)) }"
          >
            <button class="calendar-day-number" type="button" @click="openDay(day)">
              {{ day }}
            </button>
            <button
              v-for="event in eventsForDay(day)"
              :key="`${event.kind}-${event.id}`"
              class="calendar-event"
              :class="{ done: event.completed, todo: event.kind === 'todo' }"
              type="button"
              @click.stop="toggleEvent(event)"
            >
              {{ event.title }}
            </button>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="day-list">
          <div v-if="!dayEvents().length" class="empty">这一天没有安排</div>
          <button
            v-for="event in dayEvents()"
            :key="`${event.kind}-${event.id}`"
            class="day-event"
            :class="{ done: event.completed, todo: event.kind === 'todo' }"
            type="button"
            @click="toggleEvent(event)"
          >
            <CheckCircle2 v-if="event.completed" :size="18" color="#15803d" />
            <Circle v-else :size="18" color="#94a3b8" />
            <span class="day-event-main">
              <strong>{{ event.title }}</strong>
              <small>{{ event.kind === 'todo' ? '待办' : '计划' }}</small>
            </span>
          </button>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.calendar-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.segmented {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.segmented button {
  border: none;
  background: transparent;
  padding: 7px 16px;
  font: inherit;
  font-weight: 600;
  color: var(--text-2);
  cursor: pointer;
}

.segmented button.active {
  background: var(--primary);
  color: #fff;
}

.nav-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.icon-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.today-btn {
  padding: 6px 12px;
  font-size: 13px;
}

.calendar-label {
  min-width: 150px;
  text-align: right;
}

.year-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.year-tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 14px;
  cursor: pointer;
  font: inherit;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.year-tile:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow);
}

.year-month-name {
  font-size: 16px;
  font-weight: 700;
}

.year-count {
  color: var(--text-2);
  font-size: 12px;
}

.year-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 10px;
}

.year-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.calendar-weekday {
  text-align: center;
  font-weight: 600;
  color: #5b6b7a;
  padding: 8px 0;
}

.calendar-day {
  min-height: 96px;
  border: 1px solid #dde3e8;
  border-radius: 8px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.calendar-day.today {
  border-color: var(--primary);
  background: #f5f9ff;
}

.empty-day {
  border-color: transparent;
  background: transparent;
}

.calendar-day-number {
  align-self: flex-start;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: #5b6b7a;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}

.calendar-day.today .calendar-day-number {
  color: var(--primary);
  font-weight: 700;
}

.calendar-event {
  border: 1px solid #bfdbfe;
  background: #e8f0fe;
  color: #1d4ed8;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.calendar-event.todo {
  border-color: #99f6e4;
  background: #d9f3ef;
  color: #0f766e;
}

.calendar-event.done {
  opacity: 0.55;
  text-decoration: line-through;
}

.day-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.day-event {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 12px 14px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: var(--text);
}

.day-event.todo {
  border-color: #99f6e4;
  background: #f5fdfb;
}

.day-event.done {
  opacity: 0.6;
}

.day-event.done strong {
  text-decoration: line-through;
}

.day-event-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.day-event-main small {
  color: var(--text-2);
}

@media (max-width: 900px) {
  .calendar-toolbar {
    align-items: flex-start;
  }

  .calendar-label {
    min-width: 0;
    text-align: left;
  }

  .year-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .calendar-day {
    min-height: 72px;
    padding: 4px;
  }
}
</style>
