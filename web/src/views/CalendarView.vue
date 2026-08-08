<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { calendarApi, todosApi } from '@/api/ops'
import { plansApi } from '@/api/plans'
import type { CalendarEvent } from '@/types'

const month = ref(new Date().toISOString().slice(0, 7))
const events = ref<CalendarEvent[]>([])
const error = ref('')

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

async function load() {
  error.value = ''
  try {
    const { data } = await calendarApi.month(month.value)
    events.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

function daysInMonth(): number {
  const [year, mon] = month.value.split('-').map(Number)
  return new Date(year, mon, 0).getDate()
}

function firstOffset(): number {
  const [year, mon] = month.value.split('-').map(Number)
  const day = new Date(year, mon - 1, 1).getDay()
  return day === 0 ? 6 : day - 1
}

function eventsFor(day: number): CalendarEvent[] {
  const key = `${month.value}-${String(day).padStart(2, '0')}`
  return events.value.filter((event) => event.date === key)
}

async function toggleEvent(event: CalendarEvent) {
  if (event.kind === 'todo') {
    await todosApi.update(event.id, !event.completed)
  } else {
    await plansApi.completeItem(event.id, !event.completed)
  }
  await load()
}

function changeMonth() {
  load()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">学习日历</h1>
        <p class="page-subtitle">查看计划任务与待办，点击可标记完成</p>
      </div>
      <input v-model="month" class="input" type="month" @change="changeMonth" />
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <div class="card">
      <div class="calendar-grid">
        <div v-for="weekday in weekdays" :key="weekday" class="calendar-weekday">{{ weekday }}</div>
        <div v-for="n in firstOffset()" :key="`empty-${n}`" class="calendar-day" />
        <div v-for="day in daysInMonth()" :key="day" class="calendar-day">
          <div class="calendar-day-number">{{ day }}</div>
          <button
            v-for="event in eventsFor(day)"
            :key="`${event.kind}-${event.id}`"
            class="calendar-event"
            :class="{ done: event.completed, todo: event.kind === 'todo' }"
            type="button"
            @click="toggleEvent(event)"
          >
            {{ event.title }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.calendar-weekday {
  text-align: center;
  font-weight: 600;
  color: #5b6b7a;
  padding: 8px 0;
}

.calendar-day {
  min-height: 92px;
  border: 1px solid #dde3e8;
  border-radius: 8px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.calendar-day-number {
  font-size: 12px;
  color: #5b6b7a;
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
</style>
