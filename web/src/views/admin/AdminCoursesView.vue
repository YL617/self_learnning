<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi, type CoursePayload } from '@/api/admin'
import type { Course } from '@/types'

const items = ref<Course[]>([])
const editing = ref<Course | null>(null)
const form = ref<CoursePayload>({
  title: '',
  platform: '',
  url: '',
  description: '',
  chapters: [],
})
const error = ref('')
const success = ref('')
const checking = ref(false)

async function load() {
  try {
    const { data } = await adminApi.courses()
    items.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

function startCreate() {
  editing.value = null
  form.value = { title: '', platform: '', url: '', description: '', chapters: [] }
}

function startEdit(course: Course) {
  editing.value = course
  form.value = {
    title: course.title,
    platform: course.platform,
    url: course.url,
    description: course.description || '',
    chapters: course.chapters.map((chapter, index) => ({
      title: chapter.title,
      order_index: chapter.order_index || index + 1,
    })),
  }
}

async function save() {
  error.value = ''
  success.value = ''
  try {
    if (editing.value) {
      await adminApi.updateCourse(editing.value.id, form.value)
    } else {
      await adminApi.createCourse(form.value)
    }
    success.value = '保存成功'
    await load()
    startCreate()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '保存失败'
  }
}

async function remove(course: Course) {
  if (!window.confirm(`确定删除课程「${course.title}」吗？`)) return
  try {
    await adminApi.deleteCourse(course.id)
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

function addChapter() {
  form.value.chapters.push({ title: '', order_index: form.value.chapters.length + 1 })
}

async function checkHealth() {
  if (checking.value) return
  checking.value = true
  error.value = ''
  success.value = ''
  try {
    const { data } = await adminApi.checkCourseHealth()
    success.value = `链接校验完成：正常 ${data.ok} 个，待核验 ${data.bad + (data.unknown || 0)} 个`
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '校验失败'
  } finally {
    checking.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">课程管理</h1>
        <p class="page-subtitle">维护公开课程与章节</p>
      </div>
      <div class="row gap">
        <button class="btn btn-outline" type="button" :disabled="checking" @click="checkHealth">
          {{ checking ? '校验中...' : '校验链接' }}
        </button>
        <button class="btn btn-primary" type="button" @click="startCreate">新增课程</button>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="card">
      <h2>{{ editing ? '编辑课程' : '新增课程' }}</h2>
      <div class="form-grid">
        <div class="field">
          <span>标题</span>
          <input v-model="form.title" class="input" />
        </div>
        <div class="field">
          <span>平台</span>
          <input v-model="form.platform" class="input" />
        </div>
        <div class="field">
          <span>链接</span>
          <input v-model="form.url" class="input" />
        </div>
        <div class="field">
          <span>简介</span>
          <input v-model="form.description" class="input" />
        </div>
      </div>
      <h3 style="margin: 14px 0 8px">章节</h3>
      <div class="form-grid">
        <div v-for="(chapter, index) in form.chapters" :key="index" class="field">
          <span>第 {{ index + 1 }} 章</span>
          <input v-model="chapter.title" class="input" />
        </div>
      </div>
      <div class="row gap" style="margin-top: 12px">
        <button class="btn btn-outline" type="button" @click="addChapter">添加章节</button>
        <button class="btn btn-primary" type="button" @click="save">保存</button>
      </div>
    </div>

    <div v-if="items.length" class="list">
      <div v-for="course in items" :key="course.id" class="card">
        <div class="row gap wrap" style="justify-content: space-between">
          <div>
            <strong>{{ course.title }}</strong>
            <div class="muted">
              {{ course.platform }} · {{ course.chapters.length }} 章
              <template v-if="course.category"> · {{ course.category }}</template>
              <template v-if="course.health_status === 'ok'"> · 链接正常</template>
              <template
                v-else-if="course.health_status === 'bad' || course.health_status === 'unknown'"
              >
                · 链接待核验
              </template>
            </div>
          </div>
          <div class="row gap">
            <button class="btn btn-outline" type="button" @click="startEdit(course)">编辑</button>
            <button class="btn btn-danger" type="button" @click="remove(course)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.text-success {
  color: #15803d;
}
</style>
