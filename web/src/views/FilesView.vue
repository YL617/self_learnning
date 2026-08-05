<script setup lang="ts">
import { FileText, RefreshCw, Sparkles, Upload } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { filesApi } from '@/api/files'
import QuestionCard from '@/components/QuestionCard.vue'
import type { DocumentItem, Question } from '@/types'

const documents = ref<DocumentItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const error = ref('')
const success = ref('')
const generated = ref<Question[]>([])
const generatingDocId = ref<number | null>(null)
const genForm = ref({ count: 5, question_type: 'choice' as 'choice' | 'fill' | 'short_answer' })

async function load() {
  try {
    const { data } = await filesApi.list()
    documents.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function upload() {
  const file = fileInput.value?.files?.[0]
  if (!file) return
  uploading.value = true
  error.value = ''
  success.value = ''
  try {
    await filesApi.upload(file)
    success.value = `${file.name} 上传成功`
    if (fileInput.value) fileInput.value.value = ''
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function parse(doc: DocumentItem) {
  error.value = ''
  success.value = ''
  try {
    const { data } = await filesApi.parse(doc.id)
    success.value = `解析完成，共 ${data.chunks} 个片段`
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '解析失败'
  }
}

async function generateQuestions(doc: DocumentItem) {
  generatingDocId.value = doc.id
  error.value = ''
  try {
    const { data } = await filesApi.generateQuestions(doc.id, genForm.value)
    generated.value = data
    success.value = `基于《${doc.filename}》生成 ${data.length} 道题目`
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '出题失败'
  } finally {
    generatingDocId.value = null
  }
}

function statusLabel(status: string): string {
  return status === 'parsed' ? '已解析' : status === 'failed' ? '解析失败' : '待解析'
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">文件出题</h1>
        <p class="page-subtitle">上传 PDF / Word / PPT / TXT，解析后基于文档内容智能出题</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div class="card">
      <h2><Upload :size="16" style="vertical-align: -2px" /> 上传学习资料</h2>
      <div class="row gap wrap">
        <input ref="fileInput" class="input" type="file" accept=".pdf,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg" />
        <button class="btn btn-primary" type="button" :disabled="uploading" @click="upload">
          <Upload :size="16" />
          {{ uploading ? '上传中...' : '上传' }}
        </button>
      </div>
    </div>

    <div class="card">
      <h2><FileText :size="16" style="vertical-align: -2px" /> 我的文档</h2>
      <div v-if="!documents.length" class="empty">还没有上传文档</div>
      <div v-else class="list">
        <div v-for="doc in documents" :key="doc.id" class="list-item">
          <div class="list-item-main">
            <div class="list-item-title">{{ doc.filename }}</div>
            <div class="list-item-sub">
              {{ doc.file_type.toUpperCase() }} · {{ doc.chunks_count }} 个片段 · {{ statusLabel(doc.status) }}
            </div>
          </div>
          <span v-if="doc.status === 'parsed'" class="badge badge-green">已解析</span>
          <span v-else class="badge badge-amber">待解析</span>
          <button class="btn btn-outline" type="button" :disabled="doc.status === 'parsed'" @click="parse(doc)">
            <RefreshCw :size="16" />
            解析
          </button>
          <button class="btn btn-teal" type="button" :disabled="doc.status !== 'parsed' || generatingDocId === doc.id" @click="generateQuestions(doc)">
            <Sparkles :size="16" />
            {{ generatingDocId === doc.id ? '出题中...' : '基于文档出题' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="generated.length" class="card">
      <h2>生成的题目</h2>
      <div class="list">
        <QuestionCard v-for="question in generated" :key="question.id" :question="question" />
      </div>
    </div>
  </section>
</template>
