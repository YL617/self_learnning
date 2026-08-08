<script setup lang="ts">
import { BarChart3 } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { reportsApi } from '@/api/ops'
import type { WeeklyReport } from '@/types'

const report = ref<WeeklyReport | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await reportsApi.weekly()
    report.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">学习周报</h1>
        <p class="page-subtitle">最近 7 天的学习数据汇总</p>
      </div>
      <BarChart3 :size="28" color="#2563eb" />
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <template v-if="report">
      <div class="grid grid-4">
        <div class="card stat-card">
          <div class="stat-value">{{ report.focus_minutes }}</div>
          <div class="stat-label">专注分钟</div>
        </div>
        <div class="card stat-card">
          <div class="stat-value">{{ report.sessions }}</div>
          <div class="stat-label">完成番茄钟</div>
        </div>
        <div class="card stat-card">
          <div class="stat-value">{{ report.answered }}</div>
          <div class="stat-label">答题数</div>
        </div>
        <div class="card stat-card">
          <div class="stat-value">{{ report.coins_earned }}</div>
          <div class="stat-label">获得智学币</div>
        </div>
      </div>
      <div class="card">
        <h2>正确率与错题</h2>
        <p class="muted">
          答题正确 {{ report.correct }} 道，新增错题 {{ report.wrong_added }} 道。
        </p>
      </div>
    </template>
  </section>
</template>
