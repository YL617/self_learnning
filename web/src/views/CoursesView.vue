<script setup lang="ts">
import { ExternalLink, GraduationCap } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { coursesApi } from '@/api/ops'
import type { Course } from '@/types'

const courses = ref<Course[]>([])
const error = ref('')
const activeCategory = ref('全部')

const categories = computed(() => {
  const set = new Set<string>()
  for (const course of courses.value) {
    if (course.category) set.add(course.category)
  }
  return ['全部', ...Array.from(set)]
})

const filtered = computed(() =>
  activeCategory.value === '全部'
    ? courses.value
    : courses.value.filter((course) => course.category === activeCategory.value),
)

onMounted(async () => {
  try {
    const { data } = await coursesApi.list()
    courses.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">公开课程</h1>
        <p class="page-subtitle">聚合优质公开课，仅提供索引与外链跳转</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <div class="row gap" style="flex-wrap: wrap; margin-bottom: 16px">
      <button
        v-for="category in categories"
        :key="category"
        class="btn"
        :class="{ 'btn-primary': activeCategory === category }"
        type="button"
        @click="activeCategory = category"
      >
        {{ category }}
      </button>
    </div>

    <div class="grid grid-3">
      <div v-for="course in filtered" :key="course.id" class="card">
        <h2><GraduationCap :size="16" style="vertical-align: -2px" /> {{ course.title }}</h2>
        <div class="row gap" style="flex-wrap: wrap; margin: 2px 0 10px">
          <span v-if="course.category" class="badge badge-teal">{{ course.category }}</span>
          <span v-if="course.language === 'en'" class="badge badge-teal">英文</span>
          <span
            v-if="course.health_status === 'ok'"
            class="badge badge-green"
          >
            链接正常
          </span>
          <span
            v-else-if="course.health_status === 'bad' || course.health_status === 'unknown'"
            class="badge badge-amber"
          >
            链接待核验
          </span>
          <span v-else class="badge">链接未校验</span>
        </div>
        <p class="muted">{{ course.description }}</p>
        <div class="list">
          <div v-for="chapter in course.chapters" :key="chapter.id" class="list-item">
            <div class="list-item-title">{{ chapter.order_index }}. {{ chapter.title }}</div>
          </div>
        </div>
        <a class="btn btn-primary btn-block" :href="course.url" target="_blank" rel="noopener noreferrer">
          <ExternalLink :size="16" />
          前往 {{ course.platform }}
        </a>
      </div>
    </div>
  </section>
</template>
