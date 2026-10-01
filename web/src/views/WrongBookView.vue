<script setup lang="ts">
import { BookOpenCheck, CalendarClock, Sparkles } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { questionsApi } from '@/api/questions'
import QuestionCard from '@/components/QuestionCard.vue'
import type { Question, WrongBookItem } from '@/types'
import { petEvents } from '@/utils/petEvents'

const items = ref<WrongBookItem[]>([])
const dueItems = ref<WrongBookItem[]>([])
const generated = ref<Question[]>([])
const error = ref('')
const success = ref('')
const generating = ref(false)
const onlyDue = ref(false)

const visibleItems = computed(() => (onlyDue.value ? dueItems.value : items.value))
const today = new Date().toISOString().slice(0, 10)

function optionList(question: Question | null | undefined): string[] {
  if (!question?.options_json) return []
  try {
    const parsed = JSON.parse(question.options_json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

async function load() {
  try {
    const [all, due] = await Promise.allSettled([
      questionsApi.wrongBook(),
      questionsApi.dueWrongBook(),
    ])
    if (all.status === 'fulfilled') items.value = all.value.data
    if (due.status === 'fulfilled') dueItems.value = due.value.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function toggleMastered(item: WrongBookItem) {
  try {
    const next = !item.mastered
    await questionsApi.updateWrongItem(item.id, next)
    await load()
    if (next) {
      petEvents.emit({ kind: 'wrong-book' })
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '更新失败'
  }
}

async function reviewOnce(item: WrongBookItem) {
  error.value = ''
  try {
    await questionsApi.reviewWrongItem(item.id)
    success.value = '已完成一次复习，下次复习时间已更新'
    await load()
    petEvents.emit({ kind: 'wrong-book' })
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '复习失败'
  }
}

async function retry(item: WrongBookItem) {
  if (!item.question) return
  generating.value = true
  error.value = ''
  try {
    const { data } = await questionsApi.generate({
      subject: item.question.subject,
      knowledge_point: item.question.knowledge_point,
      count: 3,
      question_type: 'choice',
      reference_question_id: item.question_id,
    })
    generated.value = data
    success.value = `已基于「${item.question.knowledge_point}」生成 3 道同类题`
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '生成失败'
  } finally {
    generating.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">错题本</h1>
        <p class="page-subtitle">沉淀做错的题目，通过举一反三巩固薄弱知识点</p>
      </div>
      <div class="row gap">
        <button
          class="btn"
          :class="onlyDue ? 'btn-primary' : 'btn-outline'"
          type="button"
          @click="onlyDue = !onlyDue"
        >
          <CalendarClock :size="16" />
          {{ onlyDue ? '只看今日需要复习' : '全部错题' }}（{{
            onlyDue ? dueItems.length : items.length
          }}）
        </button>
      </div>
    </div>

    <div v-if="dueItems.length" class="card due-banner">
      <CalendarClock :size="18" />
      <div>
        <strong>今日需要复习 {{ dueItems.length }} 题</strong>
        <p class="muted">
          按间隔复习到期题目：1 天 → 3 天 → 7 天 → 15 天 → 30 天，连续答对会自动标记为已掌握。
        </p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div v-if="!visibleItems.length" class="empty">
      <BookOpenCheck :size="28" style="margin-bottom: 8px" />
      <div>{{ onlyDue ? '今天没有到期需要复习的错题' : '还没有错题，继续保持' }}</div>
    </div>
    <div v-else class="list">
      <div v-for="item in visibleItems" :key="item.id" class="card">
        <div class="question-meta" style="display: flex; gap: 8px; margin-bottom: 8px">
          <span class="badge">{{ item.question?.subject }}</span>
          <span class="badge badge-amber">复习 {{ item.review_count }} 次</span>
          <span class="badge badge-amber">阶段 {{ item.review_stage }}/5</span>
          <span v-if="item.mastered" class="badge badge-green">已掌握</span>
          <span
            v-else-if="item.next_review_date && item.next_review_date <= today"
            class="badge badge-red"
          >
            今日需要复习
          </span>
        </div>
        <h3 class="question-stem">{{ item.question?.stem }}</h3>
        <div v-if="optionList(item.question).length" class="option-list" style="margin-top: 10px">
          <div
            v-for="option in optionList(item.question)"
            :key="option"
            class="option-item option-item-static"
          >
            <span>{{ option }}</span>
          </div>
        </div>
        <p v-if="!item.mastered && item.next_review_date" class="muted" style="margin: 8px 0">
          下次复习：{{ item.next_review_date }}
        </p>
        <p v-else-if="item.mastered" class="muted" style="margin: 8px 0">
          已掌握，不再进入复习队列
        </p>
        <p v-if="item.question?.analysis" class="muted" style="margin: 8px 0">
          {{ item.question.analysis }}
        </p>
        <div class="row gap wrap">
          <button class="btn btn-outline" type="button" :disabled="generating" @click="retry(item)">
            <Sparkles :size="16" />
            举一反三
          </button>
          <button v-if="!item.mastered" class="btn btn-teal" type="button" @click="reviewOnce(item)">
            复习一次
          </button>
          <button class="btn btn-ghost" type="button" @click="toggleMastered(item)">
            {{ item.mastered ? '取消掌握' : '标记已掌握' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="generated.length" class="card">
      <h2>同类练习</h2>
      <div class="list">
        <QuestionCard v-for="question in generated" :key="question.id" :question="question" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.option-item-static {
  cursor: default;
}

.due-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-left: 3px solid var(--amber);
}

.due-banner p {
  margin: 2px 0 0;
  font-size: 12px;
}

.badge-red {
  background: var(--danger-soft);
  color: var(--danger);
}
</style>
