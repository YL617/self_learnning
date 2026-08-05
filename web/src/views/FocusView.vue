<script setup lang="ts">
import { Play, Square, Timer } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import type { FocusSession, FocusStats } from '@/types'

const stats = ref<FocusStats>({ total_minutes: 0, session_count: 0, today_minutes: 0 })
const taskLabel = ref('专注学习')
const duration = ref(25)
const activeSession = ref<FocusSession | null>(null)
const remainingSeconds = ref(0)
const timerHandle = ref<number | null>(null)
const error = ref('')

const displayTime = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60)
  const seconds = remainingSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

async function loadStats() {
  try {
    const { data } = await focusApi.stats()
    stats.value = data
  } catch {
    stats.value = { total_minutes: 0, session_count: 0, today_minutes: 0 }
  }
}

async function start() {
  error.value = ''
  try {
    const { data } = await focusApi.startSession(taskLabel.value, duration.value)
    activeSession.value = data
    remainingSeconds.value = data.duration_minutes * 60
    timerHandle.value = window.setInterval(() => {
      remainingSeconds.value -= 1
      if (remainingSeconds.value <= 0) complete()
    }, 1000)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '开始失败'
  }
}

async function complete() {
  if (timerHandle.value !== null) {
    window.clearInterval(timerHandle.value)
    timerHandle.value = null
  }
  if (!activeSession.value) return
  const session = activeSession.value
  activeSession.value = null
  try {
    await focusApi.completeSession(session.id)
    await loadStats()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '记录失败'
  }
}

onMounted(loadStats)
onBeforeUnmount(() => {
  if (timerHandle.value !== null) window.clearInterval(timerHandle.value)
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
        <h2><Timer :size="16" style="vertical-align: -2px" /> 番茄钟</h2>
        <template v-if="!activeSession">
          <div class="form-grid">
            <div class="field">
              <span>任务标签</span>
              <input v-model="taskLabel" class="input" />
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
          <button class="btn btn-primary" style="margin-top: 12px" type="button" @click="start">
            <Play :size="16" />
            开始专注
          </button>
        </template>
        <template v-else>
          <div class="timer-display">{{ displayTime }}</div>
          <p style="text-align: center" class="muted">{{ activeSession.task_label }}</p>
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
  </section>
</template>
