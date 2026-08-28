<script setup lang="ts">
import {
  BookOpenCheck,
  Camera,
  CalendarDays,
  FileQuestion,
  KeyRound,
  Sparkles,
  Timer,
  UserRound,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import { plansApi } from '@/api/plans'
import { questionsApi } from '@/api/questions'
import { usersApi } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import type { FocusStats, MembershipInfo, StudyPlan } from '@/types'

const auth = useAuthStore()
const nickname = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const stats = ref<FocusStats>({ total_minutes: 0, session_count: 0, today_minutes: 0 })
const plans = ref<StudyPlan[]>([])
const questionCount = ref(0)
const wrongCount = ref(0)
const membership = ref<MembershipInfo | null>(null)
const activationCode = ref('')
const error = ref('')
const success = ref('')

const displayName = computed(
  () => auth.user?.nickname || auth.user?.username || '同学',
)
const avatarUrl = computed(() => auth.user?.avatar_url || '')
const tierName = computed(() => {
  const level = membership.value?.effective_membership || auth.user?.membership_level || 'free'
  const names: Record<string, string> = {
    free: '免费版',
    basic: '基础会员',
    advanced: '进阶会员',
    full: '完整会员',
  }
  return names[level] || level
})

async function load() {
  error.value = ''
  try {
    const user = await auth.me()
    nickname.value = user.nickname || user.username || ''
    const [statsRes, plansRes, questionsRes, wrongRes] = await Promise.allSettled([
      focusApi.stats(),
      plansApi.list(),
      questionsApi.list(),
      questionsApi.wrongBook(),
    ])
    if (statsRes.status === 'fulfilled') stats.value = statsRes.value.data
    if (plansRes.status === 'fulfilled') plans.value = plansRes.value.data
    if (questionsRes.status === 'fulfilled') questionCount.value = questionsRes.value.data.length
    if (wrongRes.status === 'fulfilled') wrongCount.value = wrongRes.value.data.length
    const membershipRes = await usersApi.membership()
    membership.value = membershipRes.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function activateCode() {
  error.value = ''
  success.value = ''
  if (!activationCode.value.trim()) {
    error.value = '请输入激活码'
    return
  }
  try {
    const { data } = await usersApi.activateCode(activationCode.value.trim())
    auth.setUser(data)
    const membershipRes = await usersApi.membership()
    membership.value = membershipRes.data
    activationCode.value = ''
    success.value = '激活成功，会员权益已生效'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '激活失败'
  }
}

async function saveNickname() {
  try {
    const { data } = await usersApi.updateMe(nickname.value.trim())
    auth.setUser(data)
    success.value = '昵称已更新'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '昵称更新失败'
  }
}

async function changePassword() {
  error.value = ''
  success.value = ''
  if (!oldPassword.value || !newPassword.value) {
    error.value = '请填写原密码和新密码'
    return
  }
  try {
    await usersApi.changePassword(oldPassword.value, newPassword.value)
    oldPassword.value = ''
    newPassword.value = ''
    success.value = '密码修改成功'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '密码修改失败'
  }
}

async function onAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const { data } = await usersApi.uploadAvatar(file)
    auth.setUser(data)
    success.value = '头像已更新'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '头像上传失败'
  } finally {
    input.value = ''
  }
}

const completedPlanCount = computed(() =>
  plans.value.reduce(
    (sum, plan) => sum + plan.items.filter((item) => item.completed).length,
    0,
  ),
)

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">个人中心</h1>
        <p class="page-subtitle">{{ displayName }}，保持你的学习节奏</p>
      </div>
      <span class="badge badge-teal">
        <Sparkles :size="13" />
        {{ tierName }}
      </span>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="grid grid-2">
      <div class="card">
        <h2><Sparkles :size="16" style="vertical-align: -2px" /> 会员中心</h2>
        <div class="membership-summary">
          <div>
            <span class="stat-label">当前权益</span>
            <div class="stat-value">{{ tierName }}</div>
          </div>
          <div v-if="membership">
            <span class="stat-label">AI 额度</span>
            <div class="stat-value">
              {{ membership.ai_quota_used }}/{{ membership.ai_quota_total }}
            </div>
          </div>
        </div>
        <p v-if="membership?.trial_active" class="muted">
          试用期剩余 {{ membership.trial_days_left }} 天，期间开放全部功能
        </p>
        <p v-else-if="membership?.membership_expires_at" class="muted">
          会员有效期至 {{ membership.membership_expires_at.slice(0, 10) }}
        </p>
        <p v-else class="muted">当前为免费版，兑换激活码即可升级</p>
        <div class="row gap" style="margin-top: 12px">
          <input
            v-model="activationCode"
            class="input"
            maxlength="64"
            placeholder="输入激活码"
          />
          <button class="btn btn-primary" type="button" @click="activateCode">
            兑换
          </button>
        </div>
      </div>

      <div class="card">
        <h2><UserRound :size="16" style="vertical-align: -2px" /> 账号资料</h2>
        <div class="row gap" style="align-items: flex-start">
          <div class="avatar-wrap">
            <img v-if="avatarUrl" :src="avatarUrl" alt="头像" />
            <span v-else class="avatar-placeholder">{{ displayName.slice(0, 1) }}</span>
            <label class="avatar-edit" title="上传头像">
              <Camera :size="14" />
              <input type="file" accept="image/*" @change="onAvatarChange" />
            </label>
          </div>
          <div style="flex: 1; min-width: 0">
            <div class="field">
              <span>昵称</span>
              <input v-model="nickname" class="input" maxlength="64" />
            </div>
            <button class="btn btn-primary" type="button" @click="saveNickname">
              保存昵称
            </button>
          </div>
        </div>

        <h2 style="margin-top: 18px">
          <KeyRound :size="16" style="vertical-align: -2px" /> 修改密码
        </h2>
        <div class="form-grid">
          <div class="field">
            <span>原密码</span>
            <input v-model="oldPassword" class="input" type="password" />
          </div>
          <div class="field">
            <span>新密码</span>
            <input v-model="newPassword" class="input" type="password" />
          </div>
        </div>
        <button class="btn btn-outline" type="button" @click="changePassword">
          修改密码
        </button>
      </div>

      <div class="card">
      <h2>学习数据</h2>
      <div class="grid grid-2">
        <div class="stat-card">
          <div class="stat-icon stat-icon-timer"><Timer :size="20" /></div>
          <div>
            <div class="stat-value">{{ stats.total_minutes }}</div>
            <div class="stat-label">累计专注分钟</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon stat-icon-plan"><CalendarDays :size="20" /></div>
          <div>
            <div class="stat-value">{{ stats.session_count }}</div>
            <div class="stat-label">完成番茄钟</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon stat-icon-plan"><CalendarDays :size="20" /></div>
          <div>
            <div class="stat-value">{{ plans.length }}</div>
            <div class="stat-label">学习计划</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon stat-icon-question"><FileQuestion :size="20" /></div>
          <div>
            <div class="stat-value">{{ completedPlanCount }}</div>
            <div class="stat-label">完成任务</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon stat-icon-question"><FileQuestion :size="20" /></div>
          <div>
            <div class="stat-value">{{ questionCount }}</div>
            <div class="stat-label">练习题目</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon stat-icon-wrong"><BookOpenCheck :size="20" /></div>
          <div>
            <div class="stat-value">{{ wrongCount }}</div>
            <div class="stat-label">错题</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>学情资料</h2>
      <div v-if="auth.user?.profile" class="grid grid-4 profile-grid">
        <div class="profile-item">
          <span>专业</span>
          <strong>{{ auth.user.profile.major || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>年级</span>
          <strong>{{ auth.user.profile.grade || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>目标</span>
          <strong>{{ auth.user.profile.goals || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>每日学习</span>
          <strong>{{ auth.user.profile.daily_study_minutes }} 分钟</strong>
        </div>
        <div class="profile-item">
          <span>薄弱点</span>
          <strong>{{ auth.user.profile.weak_subjects || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>学习方式</span>
          <strong>{{ auth.user.profile.learning_style || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>时间安排</span>
          <strong>{{ auth.user.profile.available_time_slots || '未填写' }}</strong>
        </div>
        <div class="profile-item">
          <span>学情完善</span>
          <strong>{{ auth.user.profile.onboarding_completed ? '已完成' : '未完成' }}</strong>
        </div>
      </div>
      <div v-else class="empty">暂无学情资料</div>
      <router-link to="/onboarding" class="btn btn-outline" style="margin-top: 14px">
        完善学情
      </router-link>
    </div>
  </section>
</template>

<style scoped>
.text-success {
  color: var(--success);
}

.membership-summary {
  display: flex;
  gap: 28px;
  margin-bottom: 8px;
}

.avatar-wrap {
  position: relative;
  width: 84px;
  height: 84px;
  flex-shrink: 0;
}

.avatar-wrap img,
.avatar-placeholder {
  width: 84px;
  height: 84px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--border);
  background: var(--primary-soft);
  color: var(--primary);
  display: grid;
  place-items: center;
  font-size: 30px;
  font-weight: 700;
}

.avatar-edit {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  border: 2px solid var(--surface);
}

.avatar-edit input {
  display: none;
}

.profile-grid {
  gap: 14px;
}

.profile-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.profile-item span {
  color: var(--text-2);
  font-size: 12px;
}

.profile-item strong {
  font-size: 14px;
  word-break: break-word;
}

.stat-icon-timer {
  background: var(--teal-soft);
  color: var(--teal);
}

.stat-icon-plan {
  background: #e8edf7;
  color: #415f91;
}

.stat-icon-question {
  background: var(--amber-soft);
  color: var(--amber);
}

.stat-icon-wrong {
  background: var(--danger-soft);
  color: var(--danger);
}
</style>
