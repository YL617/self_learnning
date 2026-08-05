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
      <h2><Sparkles :size="16" style="vertical-align: -2px" /> 生成题目</h2>
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
      <button class="btn btn-primary" style="margin-top: 12px" type="button" :disabled="loading" @click="generate">
        <Sparkles :size="16" />
        {{ loading ? '生成中...' : '生成题目' }}
      </button>
      <p v-if="error" class="text-danger" style="margin: 10px 0 0">{{ error }}</p>
      <p v-if="success" style="margin: 10px 0 0; color: #15803d">{{ success }}</p>
    </div>

    <div v-if="questions.length">
      <div class="row space-between" style="margin-bottom: 10px">
        <h2 style="margin: 0"><FileQuestion :size="16" style="vertical-align: -2px" /> 题目列表</h2>
      </div>
      <div class="list">
        <QuestionCard v-for="question in questions" :key="question.id" :question="question" />
      </div>
    </div>
    <div v-else class="empty">还没有题目，先在上面生成一组吧</div>
  </section>
</template>
