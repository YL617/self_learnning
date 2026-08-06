<script setup lang="ts">
import {
  BookOpenCheck,
  CalendarDays,
  Coins,
  FileQuestion,
  Timer,
} from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import { plansApi } from '@/api/plans'
import { questionsApi } from '@/api/questions'
import { useAuthStore } from '@/stores/auth'
import type { StudyPlan } from '@/types'

const auth = useAuthStore()
const stats = ref({ total_minutes: 0, session_count: 0, today_minutes: 0 })
const plans = ref<StudyPlan[]>([])
const questionCount = ref(0)
const coinBalance = ref(0)
const loading = ref(true)

onMounted(async () => {
  try {
    const [statsRes, plansRes, questionsRes, coinsRes] = await Promise.allSettled([
      focusApi.stats(),
      plansApi.list(),
      questionsApi.list(),
      focusApi.transactions(),
    ])
    if (statsRes.status === 'fulfilled') stats.value = statsRes.value.data
    if (plansRes.status === 'fulfilled') plans.value = plansRes.value.data
    if (questionsRes.status === 'fulfilled') questionCount.value = questionsRes.value.data.length
    if (coinsRes.status === 'fulfilled') {
      coinBalance.value = coinsRes.value.data.reduce((sum, tx) => sum + tx.amount, 0)
    }
  } finally {
    loading.value = false
  }
})

function planProgress(plan: StudyPlan): number {
  if (!plan.items.length) return 0
  return Math.round((plan.items.filter((item) => item.completed).length / plan.items.length) * 100)
}
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">学习总览</h1>
        <p class="page-subtitle">欢迎回来，{{ auth.user?.username || '同学' }}，保持你的学习节奏</p>
      </div>
      <div class="row gap">
        <router-link to="/onboarding" class="btn btn-outline">完善学情</router-link>
        <router-link to="/plans" class="btn btn-primary">
          <CalendarDays :size="16" />
          制定学习计划
        </router-link>
      </div>
    </div>

    <div v-if="loading" class="empty">正在加载数据...</div>
    <template v-else>
      <div class="grid grid-4">
        <div class="card stat-card">
          <div class="stat-icon"><Timer :size="22" /></div>
          <div>
            <div class="stat-value">{{ stats.total_minutes }}</div>
            <div class="stat-label">累计专注分钟</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><CalendarDays :size="22" /></div>
          <div>
            <div class="stat-value">{{ plans.length }}</div>
            <div class="stat-label">学习计划</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><FileQuestion :size="22" /></div>
          <div>
            <div class="stat-value">{{ questionCount }}</div>
            <div class="stat-label">练习题目</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><Coins :size="22" /></div>
          <div>
            <div class="stat-value">{{ coinBalance }}</div>
            <div class="stat-label">智学币余额</div>
          </div>
        </div>
      </div>

      <div class="grid grid-2">
        <div class="card">
          <h2>最近计划</h2>
          <div v-if="!plans.length" class="empty">还没有学习计划，先去创建一个吧</div>
          <div v-else class="list">
            <router-link
              v-for="plan in plans.slice(0, 4)"
              :key="plan.id"
              :to="`/plans/${plan.id}`"
              class="list-item"
              style="text-decoration: none; color: inherit"
            >
              <div class="list-item-main">
                <div class="list-item-title">{{ plan.title }}</div>
                <div class="list-item-sub">
                  {{ plan.start_date }} 至 {{ plan.end_date }} · {{ plan.items.length }} 个任务
                </div>
              </div>
              <span class="badge badge-green">{{ planProgress(plan) }}%</span>
            </router-link>
          </div>
        </div>

        <div class="card">
          <h2>今日学习</h2>
          <div class="grid grid-2">
            <div class="stat-card">
              <div class="stat-icon"><Timer :size="20" /></div>
              <div>
                <div class="stat-value">{{ stats.today_minutes }}</div>
                <div class="stat-label">今日专注</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon"><BookOpenCheck :size="20" /></div>
              <div>
                <div class="stat-value">{{ stats.session_count }}</div>
                <div class="stat-label">完成番茄钟</div>
              </div>
            </div>
          </div>
          <div class="row gap wrap" style="margin-top: 16px">
            <router-link to="/focus" class="btn btn-teal"><Timer :size="16" />开始专注</router-link>
            <router-link to="/questions" class="btn btn-outline"><FileQuestion :size="16" />开始练习</router-link>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
