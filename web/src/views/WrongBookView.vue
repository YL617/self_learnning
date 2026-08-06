<script setup lang="ts">
import { BookOpenCheck, Sparkles } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { questionsApi } from '@/api/questions'
import QuestionCard from '@/components/QuestionCard.vue'
import type { Question, WrongBookItem } from '@/types'

const items = ref<WrongBookItem[]>([])
const generated = ref<Question[]>([])
const error = ref('')
const success = ref('')
const generating = ref(false)

async function load() {
  try {
    const { data } = await questionsApi.wrongBook()
    items.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function toggleMastered(item: WrongBookItem) {
  try {
    await questionsApi.updateWrongItem(item.id, !item.mastered)
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '更新失败'
  }
}

async function reviewOnce(item: WrongBookItem) {
  try {
    await questionsApi.updateWrongItem(item.id, item.mastered)
    success.value = '已完成一次复习，下次复习时间已更新'
    await load()
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
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div v-if="!items.length" class="empty">
      <BookOpenCheck :size="28" style="margin-bottom: 8px" />
      <div>还没有错题，继续保持</div>
    </div>
    <div v-else class="list">
      <div v-for="item in items" :key="item.id" class="card">
        <div class="question-meta" style="display: flex; gap: 8px; margin-bottom: 8px">
          <span class="badge">{{ item.question?.subject }}</span>
          <span class="badge badge-amber">复习 {{ item.review_count }} 次</span>
          <span class="badge badge-amber">阶段 {{ item.review_stage }}/5</span>
          <span v-if="item.mastered" class="badge badge-green">已掌握</span>
        </div>
        <h3 class="question-stem">{{ item.question?.stem }}</h3>
        <p v-if="!item.mastered && item.next_review_date" class="muted" style="margin: 8px 0">
          下次复习：{{ item.next_review_date }}
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
