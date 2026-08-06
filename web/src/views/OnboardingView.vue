<script setup lang="ts">
import { ArrowLeft, ArrowRight, Check, RotateCcw } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { onboardingApi } from '@/api/onboarding'

const router = useRouter()

const form = ref({
  major: '',
  grade: '',
  goals: [] as string[],
  weekly_minutes: 420 as number | 'unknown',
  learning_style: [] as string[],
  pain_point: [] as string[],
  school_level: '',
  available_time_slots: [] as string[],
})
const customGoal = ref('')
const step = ref(0)
const loading = ref(false)
const error = ref('')

const steps = [
  { title: '你的专业', desc: '用于匹配专业课程模板' },
  { title: '你的年级', desc: '用于调整学习节奏' },
  { title: '近期目标', desc: '决定第一份计划的方向' },
  { title: '每周可学习时长', desc: '决定任务量' },
  { title: '喜欢的学习方式', desc: '决定任务的形式' },
  { title: '学习痛点', desc: '选填，用于优先强化' },
  { title: '补充信息', desc: '选填，让计划更贴合你' },
]

const grades = ['大一', '大二', '大三', '大四', '研究生', '其他']
const goals = ['期末高分', '通过四六级', '掌握编程', '考研', '考证', '留学', '巩固基础', '其他']
const durations: Array<{ label: string; value: number | 'unknown' }> = [
  { label: '少于 5 小时', value: 240 },
  { label: '5-10 小时', value: 420 },
  { label: '10-20 小时', value: 840 },
  { label: '20 小时以上', value: 1260 },
  { label: '不确定', value: 'unknown' },
]
const styles = ['看视频', '做题', '读教材', '混合学习', '不清楚']
const pains = ['计划难执行', '知识点难懂', '练习不够', '时间不够', '容易拖延', '不清楚', '没有明显痛点']
const levels = ['双一流', '普通本科', '高职', '不方便回答']
const slots = ['早上', '下午', '晚上', '周末', '不固定']

const totalSteps = steps.length
const progress = computed(() => Math.round(((step.value + 1) / totalSteps) * 100))

function toggle(list: string[], value: string) {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
}

function next() {
  if (step.value < totalSteps - 1) step.value += 1
}

function back() {
  if (step.value > 0) step.value -= 1
  else router.push('/')
}

async function submit(complete: boolean) {
  loading.value = true
  error.value = ''
  try {
    const goalsList = [...form.value.goals]
    if (customGoal.value.trim()) goalsList.push(customGoal.value.trim())
    await onboardingApi.submit({
      major: form.value.major || undefined,
      grade: form.value.grade || undefined,
      goals: goalsList,
      weekly_minutes:
        form.value.weekly_minutes === 'unknown'
          ? undefined
          : form.value.weekly_minutes,
      learning_style: form.value.learning_style,
      pain_point: form.value.pain_point,
      school_level: form.value.school_level || undefined,
      available_time_slots: form.value.available_time_slots,
      generate_plan: complete,
      complete,
    })
    router.push('/')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '保存失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await onboardingApi.get()
    const profile = data.profile
    form.value.major = profile.major || ''
    form.value.grade = profile.grade || ''
    form.value.goals = profile.goals ? profile.goals.split('、').filter(Boolean) : []
    form.value.weekly_minutes = profile.weekly_study_minutes || 420
    form.value.learning_style = parseList(profile.learning_style)
    form.value.pain_point = parseList(profile.pain_point)
    form.value.school_level = profile.school_level || ''
    form.value.available_time_slots = parseList(profile.available_time_slots)
  } catch {
    // 新用户没有历史问卷数据，使用默认值
  }
})

function parseList(value?: string | null): string[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
</script>

<template>
  <div class="onboarding-screen">
    <div class="onboarding-card">
      <div class="onboarding-head">
        <button class="btn btn-ghost" type="button" @click="back">
          <ArrowLeft :size="16" />
          返回
        </button>
        <div class="onboarding-progress">
          <div class="progress-label">
            <span>{{ steps[step].title }}</span>
            <span>{{ step + 1 }}/{{ totalSteps }}</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" :style="{ width: `${progress}%` }" />
          </div>
        </div>
        <button class="btn btn-ghost" type="button" @click="submit(false)">
          稍后填写
        </button>
      </div>

      <div class="onboarding-body">
        <h1>{{ steps[step].title }}</h1>
        <p class="page-subtitle">{{ steps[step].desc }}</p>

        <template v-if="step === 0">
          <input v-model="form.major" class="input input-lg" placeholder="例如：计算机科学与技术" />
          <div class="option-chips">
            <button
              v-for="option in ['计算机科学与技术', '软件工程', '电子信息', '法学', '医学', '经管']"
              :key="option"
              class="chip"
              :class="{ selected: form.major === option }"
              type="button"
              @click="form.major = option"
            >
              {{ option }}
            </button>
          </div>
        </template>

        <template v-else-if="step === 1">
          <div class="option-grid">
            <button
              v-for="option in grades"
              :key="option"
              class="option-card"
              :class="{ selected: form.grade === option }"
              type="button"
              @click="form.grade = option"
            >
              <Check v-if="form.grade === option" :size="16" />
              {{ option }}
            </button>
          </div>
        </template>

        <template v-else-if="step === 2">
          <div class="option-grid">
            <button
              v-for="option in goals"
              :key="option"
              class="option-card"
              :class="{ selected: form.goals.includes(option) }"
              type="button"
              @click="toggle(form.goals, option)"
            >
              <Check v-if="form.goals.includes(option)" :size="16" />
              {{ option }}
            </button>
          </div>
          <input v-model="customGoal" class="input" placeholder="自定义目标（选填）" />
        </template>

        <template v-else-if="step === 3">
          <div class="option-grid">
            <button
              v-for="option in durations"
              :key="option.value"
              class="option-card"
              :class="{ selected: form.weekly_minutes === option.value }"
              type="button"
              @click="form.weekly_minutes = option.value"
            >
              <Check v-if="form.weekly_minutes === option.value" :size="16" />
              {{ option.label }}
            </button>
          </div>
        </template>

        <template v-else-if="step === 4">
          <div class="option-grid">
            <button
              v-for="option in styles"
              :key="option"
              class="option-card"
              :class="{ selected: form.learning_style.includes(option) }"
              type="button"
              @click="toggle(form.learning_style, option)"
            >
              <Check v-if="form.learning_style.includes(option)" :size="16" />
              {{ option }}
            </button>
          </div>
        </template>

        <template v-else-if="step === 5">
          <div class="option-grid">
            <button
              v-for="option in pains"
              :key="option"
              class="option-card"
              :class="{ selected: form.pain_point.includes(option) }"
              type="button"
              @click="toggle(form.pain_point, option)"
            >
              <Check v-if="form.pain_point.includes(option)" :size="16" />
              {{ option }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="field">
            <span>学校层次（选填）</span>
            <div class="option-chips">
              <button
                v-for="option in levels"
                :key="option"
                class="chip"
                :class="{ selected: form.school_level === option }"
                type="button"
                @click="form.school_level = option"
              >
                {{ option }}
              </button>
            </div>
          </div>
          <div class="field" style="margin-top: 14px">
            <span>常用学习时间段（选填）</span>
            <div class="option-chips">
              <button
                v-for="option in slots"
                :key="option"
                class="chip"
                :class="{ selected: form.available_time_slots.includes(option) }"
                type="button"
                @click="toggle(form.available_time_slots, option)"
              >
                {{ option }}
              </button>
            </div>
          </div>
        </template>

        <p v-if="error" class="text-danger">{{ error }}</p>
      </div>

      <div class="onboarding-foot">
        <button class="btn btn-ghost" type="button" @click="next">
          <RotateCcw :size="16" />
          跳过此题
        </button>
        <button
          v-if="step < totalSteps - 1"
          class="btn btn-primary"
          type="button"
          @click="next"
        >
          下一步
          <ArrowRight :size="16" />
        </button>
        <button v-else class="btn btn-primary" type="button" :disabled="loading" @click="submit(true)">
          <Check :size="16" />
          {{ loading ? '生成中...' : '完成并生成计划' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.onboarding-screen {
  min-height: 100vh;
  background: var(--bg);
  display: grid;
  place-items: center;
  padding: 24px;
}

.onboarding-card {
  width: 100%;
  max-width: 680px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  min-height: 520px;
}

.onboarding-head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.onboarding-progress {
  flex: 1;
}

.onboarding-body {
  flex: 1;
  padding: 28px 24px;
}

.onboarding-body h1 {
  margin: 0 0 6px;
  font-size: 22px;
}

.onboarding-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

.input-lg {
  padding: 14px 12px;
  font-size: 16px;
}

.option-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
}

.option-card {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  padding: 12px 14px;
  font: inherit;
  cursor: pointer;
  color: var(--text);
}

.option-card.selected {
  border-color: var(--primary);
  background: #f0f6ff;
  color: var(--primary);
  font-weight: 600;
}

.option-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  padding: 8px 14px;
  font: inherit;
  cursor: pointer;
  color: var(--text-2);
}

.chip.selected {
  border-color: var(--primary);
  background: #f0f6ff;
  color: var(--primary);
  font-weight: 600;
}

@media (max-width: 600px) {
  .onboarding-screen {
    padding: 12px;
  }

  .onboarding-card {
    min-height: calc(100vh - 24px);
  }

  .option-grid {
    grid-template-columns: 1fr;
  }
}
</style>
