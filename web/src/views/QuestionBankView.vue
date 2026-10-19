<script setup lang="ts">
import { ArrowLeft, BookOpen, RefreshCw, Search } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { questionsApi, type QuestionBankParams } from '@/api/questions'
import QuestionCard from '@/components/QuestionCard.vue'
import type { KnowledgePoint, Question } from '@/types'

const route = useRoute()
const router = useRouter()
const subject = ref('')
const difficulty = ref('')
const knowledgePoint = ref('')
const concepts = ref<KnowledgePoint[]>([])
const metadataError = ref('')
const questions = ref<Question[]>([])
const selected = ref<Question | null>(null)
const loading = ref(false)
const error = ref('')
const saved = ref(false)
const practiceTitle = ref<HTMLElement | null>(null)
const difficultyNames: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' }
const subjects = computed(() => [...new Set(concepts.value.map(kp => kp.subject))].sort())
const availableConcepts = computed(() => concepts.value.filter(kp => !subject.value.trim() || kp.subject === subject.value.trim()))
let requestId = 0
let metadataRequestId = 0

function queryValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

async function loadConcepts() {
  const id = ++metadataRequestId
  metadataError.value = ''
  try {
    const { data } = await knowledgePointsApi.list({ node_type: 'concept' })
    if (id === metadataRequestId) concepts.value = data.filter(kp => kp.node_type === 'concept' && kp.status === 'active')
  } catch {
    if (id === metadataRequestId) metadataError.value = '知识点筛选暂不可用'
  }
}

async function loadQuestions() {
  const id = ++requestId
  subject.value = queryValue(route.query.subject)
  difficulty.value = queryValue(route.query.difficulty)
  knowledgePoint.value = queryValue(route.query.knowledge_point_id)
  selected.value = null
  saved.value = false
  questions.value = []
  error.value = ''
  const kpId = knowledgePoint.value ? Number(knowledgePoint.value) : undefined
  const repeatedFilter = ['subject', 'difficulty', 'knowledge_point_id'].some(key => Array.isArray(route.query[key]))
  if (repeatedFilter || (difficulty.value && !['easy', 'medium', 'hard'].includes(difficulty.value)) ||
      (kpId !== undefined && (!Number.isSafeInteger(kpId) || kpId <= 0))) {
    error.value = '筛选条件无效，请重置后重新选择'
    loading.value = false
    return
  }
  loading.value = true
  try {
    const params: QuestionBankParams = {
      subject: subject.value.trim() || undefined,
      difficulty: (difficulty.value || undefined) as QuestionBankParams['difficulty'],
      knowledge_point_id: kpId,
      limit: 100,
    }
    const { data } = await questionsApi.questionBank(params)
    if (id === requestId) questions.value = data
  } catch {
    if (id === requestId) error.value = '题库加载失败，请稍后重试'
  } finally {
    if (id === requestId) loading.value = false
  }
}

async function search(reset = false) {
  const query: Record<string, string> = {}
  if (!reset) {
    if (subject.value.trim()) query.subject = subject.value.trim()
    if (difficulty.value) query.difficulty = difficulty.value
    if (knowledgePoint.value) query.knowledge_point_id = knowledgePoint.value
  }
  const target = { path: '/question-bank', query }
  if (router.resolve(target).fullPath === route.fullPath) await loadQuestions()
  else await router.push(target)
}

function changeSubject() {
  knowledgePoint.value = ''
}

async function start(question: Question) {
  selected.value = question
  saved.value = false
  await nextTick()
  practiceTitle.value?.focus()
}

function closePractice() {
  const id = selected.value?.id
  selected.value = null
  saved.value = false
  nextTick(() => document.getElementById(`bank-start-${id}`)?.focus())
}

watch(() => route.query, loadQuestions, { immediate: true })
onMounted(loadConcepts)
onBeforeUnmount(() => { requestId++; metadataRequestId++ })
</script>

<template>
  <section class="page bank-page">
    <div class="page-head">
      <div><h1 class="page-title">共享题库</h1><p class="page-subtitle">已审核发布的练习题</p></div>
      <router-link class="btn btn-ghost" to="/questions"><BookOpen :size="16" />智能练习</router-link>
    </div>

    <form class="bank-filters" aria-label="题库筛选" @submit.prevent="search()">
      <label class="field">学科
        <input v-model="subject" class="input" list="bank-subjects" placeholder="全部学科" @input="changeSubject" />
        <datalist id="bank-subjects"><option v-for="item in subjects" :key="item" :value="item" /></datalist>
      </label>
      <label class="field">知识点
        <select v-model="knowledgePoint" class="select" :disabled="!!metadataError">
          <option value="">全部知识点</option>
          <option v-if="knowledgePoint && !availableConcepts.some(kp => String(kp.id) === knowledgePoint)" :value="knowledgePoint">知识点 #{{ knowledgePoint }}</option>
          <option v-for="kp in availableConcepts" :key="kp.id" :value="String(kp.id)">{{ kp.name }}（{{ kp.subject }}）</option>
        </select>
      </label>
      <label class="field">难度
        <select v-model="difficulty" class="select">
          <option value="">全部难度</option>
          <option v-for="(label, value) in difficultyNames" :key="value" :value="value">{{ label }}</option>
        </select>
      </label>
      <div class="bank-actions">
        <button class="btn btn-primary" type="submit"><Search :size="16" />筛选</button>
        <button class="btn btn-ghost" type="button" @click="search(true)">重置</button>
      </div>
    </form>
    <p v-if="metadataError" role="status" class="muted">{{ metadataError }} <button class="btn btn-ghost" type="button" @click="loadConcepts">重试</button></p>

    <div v-if="loading" role="status" class="empty-state">正在加载题库…</div>
    <div v-else-if="error" role="alert" class="empty-state">
      <p class="text-danger">{{ error }}</p>
      <button class="btn btn-ghost" type="button" @click="loadQuestions"><RefreshCw :size="16" />重试</button>
    </div>
    <template v-else-if="selected">
      <div class="bank-practice-head">
        <button class="btn btn-ghost" type="button" @click="closePractice"><ArrowLeft :size="16" />返回题目列表</button>
        <h2 ref="practiceTitle" tabindex="-1">练习</h2>
      </div>
      <QuestionCard :key="selected.id" :question="selected" @answered="saved = true" />
      <p v-if="saved" role="status" class="muted">本次答题记录已保存</p>
    </template>
    <div v-else-if="!questions.length" class="empty-state">
      <BookOpen :size="28" aria-hidden="true" /><h2>暂无符合条件的已发布题目</h2>
      <button class="btn btn-ghost" type="button" @click="search(true)">清除筛选</button>
    </div>
    <template v-else>
      <p class="muted" role="status">本次显示 {{ questions.length }} 道题<span v-if="questions.length === 100">；显示上限为100道，可缩小筛选范围</span></p>
      <ol class="bank-list">
        <li v-for="question in questions" :key="question.id" class="bank-item">
          <div class="bank-item-content">
            <div class="bank-meta"><span>{{ question.subject }}</span><span>{{ question.knowledge_point }}</span><span>{{ difficultyNames[question.difficulty || ''] || '难度未标注' }}</span></div>
            <h2>{{ question.stem }}</h2>
          </div>
          <button :id="`bank-start-${question.id}`" class="btn btn-primary" type="button" :aria-label="`练习：${question.stem}`" @click="start(question)">开始练习</button>
        </li>
      </ol>
    </template>
  </section>
</template>

<style scoped>
.bank-filters { display: grid; grid-template-columns: 1fr 1.4fr 1fr auto; gap: 16px; align-items: end; padding: 16px 0 24px; border-bottom: 1px solid var(--border); }
.bank-actions, .bank-practice-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.bank-list { list-style: none; margin: 0; padding: 0; }
.bank-item { display: flex; gap: 24px; align-items: center; justify-content: space-between; padding: 24px 0; border-bottom: 1px solid var(--border); }
.bank-item-content { min-width: 0; }
.bank-item h2 { font-size: 16px; margin: 8px 0 0; overflow-wrap: anywhere; font-weight: 600; }
.bank-meta { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--text-2); font-size: 12px; }
.bank-item > button { flex-shrink: 0; }
.bank-practice-head { margin: 20px 0; }
.bank-practice-head h2 { font-size: 18px; margin: 0; }
.bank-filters .field { min-width: 0; }
@media (max-width: 760px) { .bank-filters { grid-template-columns: 1fr 1fr; } .bank-item { align-items: flex-start; flex-direction: column; gap: 12px; } }
@media (max-width: 420px) { .bank-filters { grid-template-columns: 1fr; } }
</style>
