<template>
  <view class="page">
    <view class="card">
      <view class="head">
        <text class="step-count">{{ step + 1 }}/{{ steps.length }}</text>
        <text class="title">{{ steps[step] }}</text>
        <text class="muted">每步都可跳过，随时可回来补填</text>
      </view>

      <view class="body">
        <view v-if="step === 0">
          <text class="label">专业</text>
          <input v-model="form.major" class="input" placeholder="例如：计算机科学与技术" />
          <view class="chips">
            <text
              v-for="option in majors"
              :key="option"
              class="chip"
              :class="{ selected: form.major === option }"
              @click="form.major = option"
            >
              {{ option }}
            </text>
          </view>
        </view>

        <view v-else-if="step === 1">
          <text class="label">年级</text>
          <view class="chips">
            <text
              v-for="option in grades"
              :key="option"
              class="chip"
              :class="{ selected: form.grade === option }"
              @click="form.grade = option"
            >
              {{ option }}
            </text>
          </view>
        </view>

        <view v-else-if="step === 2">
          <text class="label">近期目标（多选）</text>
          <view class="chips">
            <text
              v-for="option in goals"
              :key="option"
              class="chip"
              :class="{ selected: form.goals.includes(option) }"
              @click="toggle(form.goals, option)"
            >
              {{ option }}
            </text>
          </view>
          <input v-model="customGoal" class="input" placeholder="自定义目标（选填）" />
        </view>

        <view v-else-if="step === 3">
          <text class="label">每周可学习时长</text>
          <view class="chips">
            <text
              v-for="option in durations"
              :key="option.value"
              class="chip"
              :class="{ selected: form.weekly_minutes === option.value }"
              @click="form.weekly_minutes = option.value"
            >
              {{ option.label }}
            </text>
          </view>
        </view>

        <view v-else-if="step === 4">
          <text class="label">喜欢的学习方式（多选）</text>
          <view class="chips">
            <text
              v-for="option in styles"
              :key="option"
              class="chip"
              :class="{ selected: form.learning_style.includes(option) }"
              @click="toggle(form.learning_style, option)"
            >
              {{ option }}
            </text>
          </view>
        </view>

        <view v-else-if="step === 5">
          <text class="label">学习痛点（多选）</text>
          <view class="chips">
            <text
              v-for="option in pains"
              :key="option"
              class="chip"
              :class="{ selected: form.pain_point.includes(option) }"
              @click="toggle(form.pain_point, option)"
            >
              {{ option }}
            </text>
          </view>
        </view>

        <view v-else>
          <text class="label">学校层次（选填）</text>
          <view class="chips">
            <text
              v-for="option in levels"
              :key="option"
              class="chip"
              :class="{ selected: form.school_level === option }"
              @click="form.school_level = option"
            >
              {{ option }}
            </text>
          </view>
          <text class="label" style="margin-top: 24rpx">常用学习时间段（选填）</text>
          <view class="chips">
            <text
              v-for="option in slots"
              :key="option"
              class="chip"
              :class="{ selected: form.available_time_slots.includes(option) }"
              @click="toggle(form.available_time_slots, option)"
            >
              {{ option }}
            </text>
          </view>
        </view>
      </view>

      <view class="foot">
        <button class="btn ghost" @click="next">跳过此题</button>
        <button class="btn primary" @click="step < steps.length - 1 ? next() : submit(true)">
          {{ step < steps.length - 1 ? "下一步" : "完成并生成计划" }}
        </button>
      </view>
      <button class="btn outline" @click="submit(false)">稍后填写</button>
      <button class="btn outline" @click="back">上一步 / 返回</button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";

import { api } from "@/api/request";

const steps = [
  "你的专业",
  "你的年级",
  "近期目标",
  "每周可学习时长",
  "喜欢的学习方式",
  "学习痛点",
  "补充信息",
];
const majors = ["计算机科学与技术", "软件工程", "电子信息", "法学", "医学", "经管"];
const grades = ["大一", "大二", "大三", "大四", "研究生", "其他"];
const goals = ["期末高分", "通过四六级", "掌握编程", "考研", "考证", "留学", "巩固基础", "其他"];
const durations: Array<{ label: string; value: number | "unknown" }> = [
  { label: "少于 5 小时", value: 240 },
  { label: "5-10 小时", value: 420 },
  { label: "10-20 小时", value: 840 },
  { label: "20 小时以上", value: 1260 },
  { label: "不确定", value: "unknown" },
];
const styles = ["看视频", "做题", "读教材", "混合学习", "不清楚"];
const pains = ["计划难执行", "知识点难懂", "练习不够", "时间不够", "容易拖延", "不清楚", "没有明显痛点"];
const levels = ["双一流", "普通本科", "高职", "不方便回答"];
const slots = ["早上", "下午", "晚上", "周末", "不固定"];

const step = ref(0);
const customGoal = ref("");
const message = ref("");
const form = ref({
  major: "",
  grade: "",
  goals: [] as string[],
  weekly_minutes: 420 as number | "unknown",
  learning_style: [] as string[],
  pain_point: [] as string[],
  school_level: "",
  available_time_slots: [] as string[],
});

function toggle(list: string[], value: string) {
  const index = list.indexOf(value);
  if (index >= 0) list.splice(index, 1);
  else list.push(value);
}

function next() {
  if (step.value < steps.length - 1) step.value += 1;
}

function back() {
  if (step.value > 0) step.value -= 1;
  else uni.navigateBack({ fail: () => uni.switchTab({ url: "/pages/index/index" }) });
}

function parseList(value?: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function submit(complete: boolean) {
  message.value = "";
  try {
    const goalsList = [...form.value.goals];
    if (customGoal.value.trim()) goalsList.push(customGoal.value.trim());
    await api.submitOnboarding({
      major: form.value.major || undefined,
      grade: form.value.grade || undefined,
      goals: goalsList,
      weekly_minutes:
        form.value.weekly_minutes === "unknown"
          ? undefined
          : form.value.weekly_minutes,
      learning_style: form.value.learning_style,
      pain_point: form.value.pain_point,
      school_level: form.value.school_level || undefined,
      available_time_slots: form.value.available_time_slots,
      generate_plan: complete,
      complete,
    });
    uni.showToast({ title: complete ? "已生成计划" : "已保存进度", icon: "success" });
    setTimeout(() => uni.switchTab({ url: "/pages/index/index" }), 600);
  } catch (err: any) {
    message.value = err?.detail || "保存失败";
  }
}

onShow(async () => {
  try {
    const data = await api.getOnboarding();
    const profile = data.profile;
    form.value.major = profile.major || "";
    form.value.grade = profile.grade || "";
    form.value.goals = profile.goals ? profile.goals.split("、").filter(Boolean) : [];
    form.value.weekly_minutes = profile.weekly_study_minutes || 420;
    form.value.learning_style = parseList(profile.learning_style);
    form.value.pain_point = parseList(profile.pain_point);
    form.value.school_level = profile.school_level || "";
    form.value.available_time_slots = parseList(profile.available_time_slots);
  } catch {
    // 新用户使用默认值
  }
});
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
}

.head {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  border-bottom: 1px solid #dde3e8;
  padding-bottom: 20rpx;
}

.step-count {
  color: #2563eb;
  font-size: 24rpx;
  font-weight: 600;
}

.title {
  font-size: 36rpx;
  font-weight: 700;
}

.muted {
  color: #5b6b7a;
  font-size: 24rpx;
}

.body {
  padding: 24rpx 0;
}

.label {
  display: block;
  color: #5b6b7a;
  font-size: 26rpx;
  margin-bottom: 16rpx;
}

.input {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
  margin-bottom: 16rpx;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 14rpx;
}

.chip {
  border: 1px solid #dde3e8;
  border-radius: 999rpx;
  padding: 12rpx 24rpx;
  font-size: 24rpx;
  color: #5b6b7a;
}

.chip.selected {
  border-color: #2563eb;
  color: #2563eb;
  background: #f0f6ff;
  font-weight: 600;
}

.foot {
  display: flex;
  gap: 16rpx;
  margin-bottom: 16rpx;
}

.btn {
  flex: 1;
  border-radius: 12rpx;
  padding: 16rpx;
  font-size: 26rpx;
  font-weight: 600;
}

.btn.primary {
  background: #2563eb;
  color: #fff;
}

.btn.ghost,
.btn.outline {
  border: 1px solid #dde3e8;
  color: #5b6b7a;
  background: #fff;
}

.message {
  display: block;
  margin-top: 12rpx;
  color: #dc2626;
  font-size: 24rpx;
}
</style>
