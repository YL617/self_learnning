<script setup lang="ts">
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  ExternalLink,
  GraduationCap,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { plansApi } from '@/api/plans'
import { coursesApi } from '@/api/ops'
import type { CourseRecommendation, StudyPlan } from '@/types'
import { petEvents } from '@/utils/petEvents'

const route = useRoute()
const router = useRouter()
const plan = ref<StudyPlan | null>(null)
const error = ref('')
const success = ref('')
const recs = ref<CourseRecommendation[]>([])
const recLoading = ref(false)
const recError = ref('')

async function load() {
  error.value = ''
  try {
    const { data } = await plansApi.get(Number(route.params.id))
    plan.value = data
    await loadCourses()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function loadCourses() {
  if (!plan.value) return
  try {
    const { data } = await plansApi.courses(plan.value.id)
    recs.value = data
  } catch {
    recs.value = []
  }
}

async function recommendCourses() {
  if (!plan.value || recLoading.value) return
  recLoading.value = true
  recError.value = ''
  try {
    const { data } = await plansApi.recommendCourses(plan.value.id)
    recs.value = data
  } catch (err: any) {
    recError.value = err?.response?.data?.detail || '推荐失败'
  } finally {
    recLoading.value = false
  }
}

async function saveRec(rec: CourseRecommendation) {
  recError.value = ''
  try {
    await coursesApi.saveRecommendation(rec.id)
    await loadCourses()
  } catch (err: any) {
    recError.value = err?.response?.data?.detail || '加入失败'
  }
}

async function dismissRec(rec: CourseRecommendation) {
  recError.value = ''
  try {
    await coursesApi.dismissRecommendation(rec.id)
    await loadCourses()
  } catch (err: any) {
    recError.value = err?.response?.data?.detail || '操作失败'
  }
}

async function toggle(itemId: number, completed: boolean) {
  const next = !completed
  await plansApi.completeItem(itemId, next)
  await load()
  if (next) {
    petEvents.emit({ kind: 'plan' })
  }
}

function progress(): number {
  if (!plan.value || !plan.value.items.length) return 0
  return Math.round(
    (plan.value.items.filter((item) => item.completed).length / plan.value.items.length) * 100,
  )
}

async function deletePlan() {
  if (!plan.value) return
  if (!window.confirm(`确定删除计划「${plan.value.title}」吗？删除后无法恢复。`)) return
  error.value = ''
  try {
    await plansApi.remove(plan.value.id)
    router.push('/plans')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

async function adjustPlan() {
  if (!plan.value) return
  error.value = ''
  success.value = ''
  try {
    const { data } = await plansApi.adjust(plan.value.id)
    plan.value = data
    success.value = '计划已按最新学习情况调整'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '调整失败'
  }
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
    <p v-if="success" style="color: #15803d">{{ success }}</p>
    <template v-if="plan">
      <div class="page-head">
        <div>
          <h1 class="page-title">{{ plan.title }}</h1>
          <p class="page-subtitle">{{ plan.goal || '暂无目标描述' }}</p>
        </div>
        <div class="row gap">
          <span class="badge badge-green">{{ progress() }}% 完成</span>
          <button class="btn btn-primary" type="button" @click="adjustPlan">
            <Sparkles :size="16" />
            AI 调整计划
          </button>
          <button class="btn btn-danger" type="button" @click="deletePlan">
            <Trash2 :size="16" />
            删除计划
          </button>
        </div>
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

      <div class="card">
        <div class="row space-between" style="margin-bottom: 4px">
          <h2 style="margin: 0">
            <GraduationCap :size="16" />
            为你推荐课程
          </h2>
          <button
            class="btn btn-outline"
            type="button"
            :disabled="recLoading"
            @click="recommendCourses"
          >
            <RefreshCw :size="15" />
            {{ recLoading ? '推荐中...' : '重新推荐' }}
          </button>
        </div>
        <p class="muted" style="margin: 2px 0 12px">
          根据计划科目、知识点与你的学习目标推荐，链接可直达课程页
        </p>
        <div v-if="!recs.length" class="empty">暂无推荐课程</div>
        <div v-else class="list">
          <div v-for="rec in recs" :key="rec.id" class="list-item">
            <div class="list-item-main">
              <div class="list-item-title">{{ rec.title }}</div>
              <div class="list-item-sub">
                {{ rec.platform }}
                <span v-if="rec.subject"> · {{ rec.subject }}</span>
                <span v-if="rec.level"> · {{ rec.level }}</span>
                <span v-if="rec.language === 'en'"> · 英文</span>
                <span v-if="rec.health_status === 'ok'"> · 链接正常</span>
                <span v-else-if="rec.health_status === 'bad'"> · 链接待核验</span>
                <span v-if="rec.status === 'saved'"> · 已加入公开课</span>
              </div>
            </div>
            <div class="row gap">
              <a
                class="btn btn-outline"
                :href="rec.url"
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink :size="15" />
                前往课程
              </a>
              <template v-if="rec.status === 'pending'">
                <button class="btn btn-primary" type="button" @click="saveRec(rec)">
                  <CheckCircle2 :size="15" />
                  加入公开课
                </button>
                <button class="btn btn-ghost" type="button" @click="dismissRec(rec)">
                  <X :size="15" />
                  忽略
                </button>
              </template>
            </div>
          </div>
        </div>
        <p v-if="recError" class="text-danger" style="margin: 10px 0 0">{{ recError }}</p>
      </div>
    </template>
  </section>
</template>
