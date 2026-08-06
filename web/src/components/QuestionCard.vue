<script setup lang="ts">
import { Check, Eye, Heart, RotateCcw, Trash2 } from 'lucide-vue-next'
import { ref } from 'vue'

import { questionsApi } from '@/api/questions'
import type { Question } from '@/types'

const props = defineProps<{ question: Question; showManage?: boolean }>()
const emit = defineEmits<{
  favorite: [question: Question]
  remove: [question: Question]
}>()

const answer = ref('')
const submitted = ref(false)
const isCorrect = ref(false)
const showAnalysis = ref(false)
const submitting = ref(false)
const error = ref('')

function parseOptions(): string[] {
  if (!props.question.options_json) return []
  try {
    const parsed = JSON.parse(props.question.options_json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

async function submitAnswer() {
  if (!answer.value.trim() || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const { data } = await questionsApi.submitAnswer(props.question.id, answer.value)
    submitted.value = true
    isCorrect.value = data.is_correct
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '提交失败'
  } finally {
    submitting.value = false
  }
}

function reset() {
  answer.value = ''
  submitted.value = false
  isCorrect.value = false
  showAnalysis.value = false
  error.value = ''
}
</script>

<template>
  <article class="card question-card">
    <div class="question-meta">
      <div class="row gap">
        <span class="badge">{{ question.subject }}</span>
        <span class="badge badge-teal">{{ question.question_type }}</span>
      </div>
      <div v-if="showManage" class="row gap">
        <button class="btn btn-ghost" type="button" title="收藏题目" @click="emit('favorite', question)">
          <Heart
            :size="16"
            :fill="question.is_favorite ? 'currentColor' : 'none'"
            :color="question.is_favorite ? '#dc2626' : '#94a3b8'"
          />
          {{ question.is_favorite ? '已收藏' : '收藏' }}
        </button>
        <button class="btn btn-ghost" type="button" title="删除题目" @click="emit('remove', question)">
          <Trash2 :size="16" color="#dc2626" />
        </button>
      </div>
    </div>
    <h3 class="question-stem">{{ question.stem }}</h3>
    <div v-if="parseOptions().length" class="option-list">
      <label v-for="option in parseOptions()" :key="option" class="option-item">
        <input v-model="answer" type="radio" :value="option.split('.')[0].trim()" :disabled="submitted" />
        <span>{{ option }}</span>
      </label>
    </div>
    <textarea
      v-else
      v-model="answer"
      class="textarea"
      :placeholder="question.question_type === 'fill' ? '填写答案' : '输入你的回答'"
      rows="3"
      :disabled="submitted"
    />

    <div class="row space-between">
      <div class="row gap">
        <button class="btn btn-primary" type="button" :disabled="submitting || submitted" @click="submitAnswer">
          <Check :size="16" />
          {{ submitted ? (isCorrect ? '回答正确' : '回答错误') : '提交答案' }}
        </button>
        <button v-if="submitted" class="btn btn-ghost" type="button" @click="showAnalysis = !showAnalysis">
          <Eye :size="16" />
          {{ showAnalysis ? '收起解析' : '查看解析' }}
        </button>
        <button v-if="submitted" class="btn btn-ghost" type="button" @click="reset">
          <RotateCcw :size="16" />
          重做
        </button>
      </div>
      <span v-if="error" class="text-danger">{{ error }}</span>
    </div>

    <div v-if="showAnalysis" class="analysis-box">
      <p><strong>参考答案：</strong>{{ question.answer }}</p>
      <p v-if="question.analysis"><strong>解析：</strong>{{ question.analysis }}</p>
    </div>
  </article>
</template>
