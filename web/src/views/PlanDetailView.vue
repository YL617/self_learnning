<script setup lang="ts">
import { ArrowLeft, CheckCircle2, Circle } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { plansApi } from '@/api/plans'
import type { StudyPlan } from '@/types'

const route = useRoute()
const plan = ref<StudyPlan | null>(null)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const { data } = await plansApi.get(Number(route.params.id))
    plan.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function toggle(itemId: number, completed: boolean) {
  await plansApi.completeItem(itemId, !completed)
  await load()
}

function progress(): number {
  if (!plan.value || !plan.value.items.length) return 0
  return Math.round(
    (plan.value.items.filter((item) => item.completed).length / plan.value.items.length) * 100,
  )
}

onMounted(load)
</script>

<template>
  <section class="page">
    <router-link to="/plans" class="btn btn-ghost" style="align-self: flex-start">
      <ArrowLeft :size="16" />
      返回计划列表
    </router-link>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <template v-if="plan">
      <div class="page-head">
        <div>
          <h1 class="page-title">{{ plan.title }}</h1>
          <p class="page-subtitle">{{ plan.goal || '暂无目标描述' }}</p>
        </div>
        <span class="badge badge-green">{{ progress() }}% 完成</span>
      </div>

      <div class="card">
        <div class="progress-label">
          <span>{{ plan.start_date }} 至 {{ plan.end_date }}</span>
          <span>{{ plan.items.filter((i) => i.completed).length }}/{{ plan.items.length }} 任务</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" :style="{ width: `${progress()}%` }" />
        </div>
      </div>

      <div class="card">
        <h2>任务清单</h2>
        <div v-if="!plan.items.length" class="empty">暂无任务</div>
        <div v-else class="list">
          <div v-for="item in plan.items" :key="item.id" class="list-item">
            <button
              class="btn"
              style="padding: 4px"
              type="button"
              :title="item.completed ? '取消完成' : '标记完成'"
              @click="toggle(item.id, item.completed)"
            >
              <CheckCircle2 v-if="item.completed" :size="20" color="#15803d" />
              <Circle v-else :size="20" color="#94a3b8" />
            </button>
            <div class="list-item-main">
              <div class="list-item-title" :class="{ muted: item.completed }">
                {{ item.title }}
              </div>
              <div class="list-item-sub">
                {{ item.subject || '综合' }} · {{ item.scheduled_date }} · {{ item.duration_minutes }} 分钟
              </div>
            </div>
            <span v-if="item.completed" class="badge badge-green">已完成</span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
