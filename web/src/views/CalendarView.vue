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
const gridOffset = computed(() => firstOffset(year.value, month.value))

const eventDaysByMonth = computed(() => {
  const result: Record<string, Set<string>> = {}
  for (const [key, events] of Object.entries(eventsByMonth.value)) {
    result[key] = new Set(events.map((event) => event.date.slice(8)))
  }
  return result
})

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

function visibleEvents(day: number): CalendarEvent[] {
  return eventsForDay(day).slice(0, 3)
}

function extraEventCount(day: number): number {
  return Math.max(0, eventsForDay(day).length - 3)
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

function yearTileClass(monthNumber: number): string {
  const count = countForMonth(monthNumber)
  if (count === 0) return ''
  if (count >= 5) return 'busy'
  return 'has-events'
}

function isWeekend(day: number): boolean {
  return (gridOffset.value + day - 1) % 7 >= 5
}

function eventKindClass(event: CalendarEvent): string {
  return event.kind === 'todo' ? 'todo' : 'plan'
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
        <div class="calendar-nav">
          <strong class="calendar-label">{{ calendarLabel }}</strong>
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
        </div>
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
            :class="yearTileClass(monthNumber)"
            type="button"
            @click="openMonth(monthNumber)"
          >
            <span class="year-month-name">{{ monthNumber }}月</span>
            <span class="year-count">{{ countForMonth(monthNumber) }} 个事件</span>
            <span class="mini-grid">
              <span v-for="weekday in weekdays" :key="`w-${weekday}`" class="mini-weekday">
                {{ weekday }}
              </span>
              <span
                v-for="n in firstOffset(year, monthNumber)"
                :key="`e-${n}`"
                class="mini-day"
              />
              <span
                v-for="day in daysInMonth(year, monthNumber)"
                :key="day"
                class="mini-day"
                :class="{
                  'has-event': eventDaysByMonth[
                    monthKey(year, monthNumber)
                  ]?.has(String(day).padStart(2, '0')),
                }"
              >
                {{ day }}
              </span>
            </span>
          </button>
        </div>
      </template>

      <template v-else-if="view === 'month'">
        <div class="calendar-grid">
          <div
            v-for="(weekday, index) in weekdays"
            :key="weekday"
            class="calendar-weekday"
            :class="{ weekend: index >= 5 }"
          >
            {{ weekday }}
          </div>
          <div
            v-for="n in gridOffset"
            :key="`empty-${n}`"
            class="calendar-day empty-day"
          />
          <div
            v-for="day in daysInMonth(year, month)"
            :key="day"
            class="calendar-day"
            :class="{
              today: isToday(dateKey(year, month, day)),
              weekend: isWeekend(day),
              'has-events': eventsForDay(day).length > 0,
            }"
            @click="openDay(day)"
          >
            <div class="calendar-day-top">
              <button
                class="calendar-day-number"
                :class="{ 'is-today': isToday(dateKey(year, month, day)) }"
                type="button"
                @click.stop="openDay(day)"
              >
                {{ day }}
              </button>
              <span v-if="extraEventCount(day)" class="day-more">
                +{{ extraEventCount(day) }}
              </span>
            </div>
            <div class="calendar-day-events">
              <button
                v-for="event in visibleEvents(day)"
                :key="`${event.kind}-${event.id}`"
                class="calendar-event"
                :class="[eventKindClass(event), { done: event.completed }]"
                type="button"
                @click.stop="toggleEvent(event)"
              >
                <span class="event-dot" />
                <span class="event-title">{{ event.title }}</span>
              </button>
            </div>
            <span v-if="eventsForDay(day).length" class="mobile-event-dots">
              <span
                v-for="event in eventsForDay(day).slice(0, 4)"
                :key="`m-${event.kind}-${event.id}`"
                class="event-dot"
                :class="eventKindClass(event)"
              />
            </span>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="day-list">
          <div class="day-list-head">
            <strong>当天安排</strong>
            <span>{{ dayEvents().length }} 项</span>
          </div>
          <div v-if="!dayEvents().length" class="empty">这一天没有安排</div>
          <button
            v-for="event in dayEvents()"
            :key="`${event.kind}-${event.id}`"
            class="day-event"
            :class="[eventKindClass(event), { done: event.completed }]"
            type="button"
            @click="toggleEvent(event)"
          >
            <CheckCircle2 v-if="event.completed" :size="20" class="check-done" />
            <Circle v-else :size="20" class="check-pending" />
            <span class="day-event-main">
              <strong>{{ event.title }}</strong>
              <small>{{ event.kind === 'todo' ? '待办' : '计划' }} · 点击切换完成状态</small>
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
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  min-width: 320px;
}

.calendar-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.calendar-label {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
}

.segmented {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #f1f4f7;
}

.segmented button {
  border: none;
  background: transparent;
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.segmented button:hover {
  color: var(--primary);
}

.segmented button.active {
  background: #fff;
  color: var(--primary);
  box-shadow: var(--shadow);
}

.nav-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  color: var(--text-2);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.icon-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: #f5f9ff;
}

.today-btn {
  padding: 6px 12px;
  font-size: 13px;
}

.year-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.year-tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 12px 14px 14px;
  cursor: pointer;
  font: inherit;
  color: var(--text);
  text-align: left;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.year-tile:hover {
  border-color: var(--primary);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}

.year-tile.has-events {
  background: #f4f8ff;
  border-color: #d3e3ff;
}

.year-tile.busy {
  background: #eef8f6;
  border-color: #bfe4dc;
}

.year-month-name {
  font-size: 15px;
  font-weight: 700;
}

.year-count {
  color: var(--text-2);
  font-size: 12px;
}

.mini-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
  width: 100%;
  margin-top: 10px;
}

.mini-weekday {
  color: #9aa7b5;
  font-size: 10px;
  text-align: center;
}

.mini-day {
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  color: #7b8a99;
  font-size: 11px;
}

.mini-day.has-event {
  background: #dfeaff;
  color: #1d4ed8;
  font-weight: 700;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
}

.calendar-weekday {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: #6b7a8a;
  padding: 6px 0 10px;
}

.calendar-weekday.weekend {
  color: #9aa7b5;
}

.calendar-day {
  min-height: 104px;
  background: #fbfcfd;
  border: 1px solid #edf1f5;
  border-radius: var(--radius);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.calendar-day:hover {
  border-color: #b9ccf5;
  background: #f7faff;
  box-shadow: 0 2px 10px rgba(16, 24, 40, 0.05);
}

.calendar-day.weekend {
  background: #f6f8fb;
}

.calendar-day.today {
  border-color: #93b4f2;
  background: #f2f7ff;
}

.empty-day {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
  cursor: default;
}

.calendar-day-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 26px;
}

.calendar-day-number {
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: #5b6b7a;
  border-radius: 50%;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s ease, color 0.15s ease;
}

.calendar-day-number:hover {
  background: #e8eef5;
  color: var(--text);
}

.calendar-day-number.is-today {
  background: var(--primary);
  color: #fff;
}

.calendar-day-number.is-today:hover {
  background: var(--primary-dark);
}

.day-more {
  padding: 1px 7px;
  border-radius: 999px;
  background: #edf1f5;
  color: var(--text-2);
  font-size: 11px;
  font-weight: 600;
}

.calendar-day-events {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 0;
}

.calendar-event {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  border-radius: 6px;
  padding: 3px 6px;
  font: inherit;
  font-size: 12px;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition: background 0.15s ease;
}

.calendar-event:hover {
  background: rgba(37, 99, 235, 0.08);
}

.event-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.event-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.calendar-event.todo .event-dot {
  background: var(--teal);
}

.calendar-event.todo:hover {
  background: rgba(15, 118, 110, 0.08);
}

.calendar-event.done {
  opacity: 0.55;
}

.calendar-event.done .event-title {
  text-decoration: line-through;
}

.mobile-event-dots {
  display: none;
}

.day-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.day-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 6px;
  border-bottom: 1px solid var(--border);
  color: var(--text-2);
  font-size: 13px;
}

.day-list-head strong {
  color: var(--text);
  font-size: 14px;
}

.day-event {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: var(--radius);
  background: #fff;
  padding: 12px 14px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: var(--text);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.day-event:hover {
  border-color: #b9ccf5;
  box-shadow: 0 2px 10px rgba(16, 24, 40, 0.05);
}

.day-event.todo {
  border-left-color: var(--teal);
}

.day-event.plan {
  border-left-color: var(--primary);
}

.day-event.done {
  background: #fafbfc;
  opacity: 0.72;
}

.day-event.done strong {
  color: var(--text-2);
  text-decoration: line-through;
}

.check-done {
  color: var(--teal);
}

.check-pending {
  color: #9aa7b5;
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

@media (max-width: 1024px) {
  .year-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .calendar-toolbar {
    align-items: flex-start;
    justify-content: flex-start;
  }

  .calendar-label {
    font-size: 18px;
  }

  .calendar-day {
    min-height: 76px;
    padding: 6px;
    gap: 4px;
  }

  .calendar-day-events {
    gap: 2px;
  }

  .calendar-event {
    padding: 2px 4px;
    font-size: 11px;
  }

  .year-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .calendar-toolbar {
    min-width: 0;
  }

  .calendar-grid {
    gap: 4px;
  }

  .calendar-day {
    min-height: 64px;
    padding: 4px;
    border-radius: 6px;
  }

  .calendar-day-number {
    width: 24px;
    height: 24px;
    font-size: 12px;
  }

  .calendar-day-events {
    display: none;
  }

  .mobile-event-dots {
    display: flex;
    gap: 3px;
    margin-top: auto;
  }

  .mobile-event-dots .event-dot {
    width: 5px;
    height: 5px;
  }

  .mobile-event-dots .event-dot.todo {
    background: var(--teal);
  }

  .mobile-event-dots .event-dot.plan {
    background: var(--primary);
  }

  .day-more {
    display: none;
  }

  .year-grid {
    gap: 8px;
  }

  .mini-day {
    height: 18px;
    font-size: 10px;
  }
}
</style>
