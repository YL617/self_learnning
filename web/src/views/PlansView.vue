<script setup lang="ts">
import { CalendarDays, Sparkles, Plus } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { plansApi } from '@/api/plans'
import type { StudyPlan } from '@/types'

const plans = ref<StudyPlan[]>([])
const loading = ref(true)
const error = ref('')
const success = ref('')

const genForm = ref({
  major: '计算机科学与技术',
  grade: '大二',
  goal: '通过四级并掌握数据结构',
  daily_minutes: 90,
  weeks: 2,
  subjects: '数据结构,英语',
})

const manualForm = ref({
  title: '',
  goal: '',
  start_date: new Date().toISOString().slice(0, 10),
  end_date: '',
})

async function load() {
  loading.value = true
  try {
    const { data } = await plansApi.list()
    plans.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function generatePlan() {
  error.value = ''
  success.value = ''
  try {
    await plansApi.generate({
      ...genForm.value,
      subjects: genForm.value.subjects
        .split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean),
    })
    success.value = '计划生成成功'
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '生成失败'
  }
}

async function createManual() {
  error.value = ''
  success.value = ''
  try {
    await plansApi.create({
      title: manualForm.value.title,
      goal: manualForm.value.goal || undefined,
      start_date: manualForm.value.start_date,
      end_date: manualForm.value.end_date,
    })
    manualForm.value.title = ''
    manualForm.value.goal = ''
    success.value = '计划创建成功'
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '创建失败'
  }
}

function progress(plan: StudyPlan): number {
  if (!plan.items.length) return 0
  return Math.round((plan.items.filter((item) => item.completed).length / plan.items.length) * 100)
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">学习计划</h1>
        <p class="page-subtitle">用 AI 生成个性化周计划，或手动创建自己的学习安排</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div class="grid grid-2">
      <div class="card">
        <h2><Sparkles :size="16" style="vertical-align: -2px" /> AI 生成计划</h2>
        <div class="form-grid">
          <div class="field">
            <span>专业</span>
            <input v-model="genForm.major" class="input" />
          </div>
          <div class="field">
            <span>年级</span>
            <input v-model="genForm.grade" class="input" />
          </div>
          <div class="field" style="grid-column: 1 / -1">
            <span>学习目标</span>
            <input v-model="genForm.goal" class="input" />
          </div>
          <div class="field">
            <span>每日时长（分钟）</span>
            <input v-model.number="genForm.daily_minutes" class="input" type="number" min="10" max="600" />
          </div>
          <div class="field">
            <span>周期（周）</span>
            <input v-model.number="genForm.weeks" class="input" type="number" min="1" max="12" />
          </div>
          <div class="field" style="grid-column: 1 / -1">
            <span>重点科目（逗号分隔）</span>
            <input v-model="genForm.subjects" class="input" />
          </div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top: 12px" type="button" @click="generatePlan">
          <Sparkles :size="16" />
          生成学习计划
        </button>
      </div>

      <div class="card">
        <h2><Plus :size="16" style="vertical-align: -2px" /> 手动创建</h2>
        <div class="form-grid">
          <div class="field" style="grid-column: 1 / -1">
            <span>计划名称</span>
            <input v-model="manualForm.title" class="input" placeholder="例如：四级冲刺计划" />
          </div>
          <div class="field" style="grid-column: 1 / -1">
            <span>目标</span>
            <textarea v-model="manualForm.goal" class="textarea" rows="2" placeholder="计划想达成什么" />
          </div>
          <div class="field">
            <span>开始日期</span>
            <input v-model="manualForm.start_date" class="input" type="date" />
          </div>
          <div class="field">
            <span>结束日期</span>
            <input v-model="manualForm.end_date" class="input" type="date" />
          </div>
        </div>
        <button class="btn btn-outline btn-block" style="margin-top: 12px" type="button" @click="createManual">
          <Plus :size="16" />
          创建计划
        </button>
      </div>
    </div>

    <div class="card">
      <h2><CalendarDays :size="16" style="vertical-align: -2px" /> 我的计划</h2>
      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="!plans.length" class="empty">还没有计划</div>
      <div v-else class="list">
        <router-link
          v-for="plan in plans"
          :key="plan.id"
          :to="`/plans/${plan.id}`"
          class="list-item"
          style="text-decoration: none; color: inherit"
        >
          <div class="list-item-main">
            <div class="list-item-title">{{ plan.title }}</div>
            <div class="list-item-sub">
              {{ plan.start_date }} 至 {{ plan.end_date }} · {{ plan.items.filter((i) => i.completed).length }}/{{ plan.items.length }} 任务完成
            </div>
            <div class="progress-track" style="margin-top: 8px">
              <div class="progress-bar" :style="{ width: `${progress(plan)}%` }" />
            </div>
          </div>
          <span class="badge badge-green">{{ progress(plan) }}%</span>
        </router-link>
      </div>
    </div>
  </section>
</template>
