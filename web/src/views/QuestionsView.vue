<script setup lang="ts">
import { FileQuestion, Sparkles } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { questionsApi } from '@/api/questions'
import QuestionCard from '@/components/QuestionCard.vue'
import type { Question } from '@/types'

const form = ref({
  subject: '数据结构',
  knowledge_point: '栈和队列',
  count: 5,
  question_type: 'choice' as 'choice' | 'fill' | 'short_answer',
})
const questions = ref<Question[]>([])
const loading = ref(false)
const error = ref('')
const success = ref('')

async function generate() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const { data } = await questionsApi.generate(form.value)
    questions.value = data
    success.value = `已生成 ${data.length} 道题目`
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '生成失败'
  } finally {
    loading.value = false
  }
}

async function load() {
  try {
    const { data } = await questionsApi.list()
    questions.value = data
  } catch {
    questions.value = []
  }
}

async function toggleFavorite(question: Question) {
  error.value = ''
  success.value = ''
  try {
    const { data } = await questionsApi.setFavorite(question.id, !question.is_favorite)
    const index = questions.value.findIndex((item) => item.id === question.id)
    if (index >= 0) questions.value[index] = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '收藏操作失败'
  }
}

async function removeQuestion(question: Question) {
  if (!window.confirm(`确定删除题目「${question.stem.slice(0, 20)}...」吗？删除后无法恢复。`)) return
  error.value = ''
  success.value = ''
  try {
    await questionsApi.remove(question.id)
    questions.value = questions.value.filter((item) => item.id !== question.id)
    success.value = '题目已删除'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">智能练习</h1>
        <p class="page-subtitle">按学科与知识点生成练习题，AI 自动判题并沉淀错题</p>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2><Sparkles :size="16" /> 生成题目</h2>
        <span class="badge badge-teal">AI 出题</span>
      </div>
      <div class="form-grid">
        <div class="field">
          <span>学科</span>
          <input v-model="form.subject" class="input" />
        </div>
        <div class="field">
          <span>知识点</span>
          <input v-model="form.knowledge_point" class="input" />
        </div>
        <div class="field">
          <span>数量</span>
          <input v-model.number="form.count" class="input" type="number" min="1" max="20" />
        </div>
        <div class="field">
          <span>题型</span>
          <select v-model="form.question_type" class="select">
            <option value="choice">单选题</option>
            <option value="fill">填空题</option>
            <option value="short_answer">简答题</option>
          </select>
        </div>
      </div>
      <div class="generate-actions">
        <button class="btn btn-primary" type="button" :disabled="loading" @click="generate">
          <Sparkles :size="16" />
          {{ loading ? '生成中...' : '生成题目' }}
        </button>
        <p v-if="error" class="text-danger">{{ error }}</p>
        <p v-if="success" class="text-success">{{ success }}</p>
      </div>
    </div>

    <div v-if="questions.length">
      <div class="row space-between list-head">
        <h2><FileQuestion :size="16" /> 题目列表</h2>
        <span class="badge">{{ questions.length }} 道</span>
      </div>
      <div class="list">
        <QuestionCard
          v-for="question in questions"
          :key="question.id"
          :question="question"
          :show-manage="true"
          @favorite="toggleFavorite"
          @remove="removeQuestion"
        />
      </div>
    </div>
    <div v-else class="empty">还没有题目，先在上面生成一组吧</div>
  </section>
</template>

<style scoped>
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.card-head h2 {
  margin: 0;
}

.generate-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.generate-actions p {
  margin: 0;
}

.list-head {
  margin-bottom: 2px;
}

.list-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 7px;
}
</style>
