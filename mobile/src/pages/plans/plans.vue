<template>
  <view class="page">
    <view class="card">
      <text class="card-title">AI 生成计划</text>
      <view class="field">
        <text>专业</text>
        <input v-model="form.major" class="input" />
      </view>
      <view class="field">
        <text>学习目标</text>
        <input v-model="form.goal" class="input" />
      </view>
      <view class="row">
        <view class="field half">
          <text>每日分钟</text>
          <input v-model.number="form.daily_minutes" class="input" type="number" />
        </view>
        <view class="field half">
          <text>周期（周）</text>
          <input v-model.number="form.weeks" class="input" type="number" />
        </view>
      </view>
      <button class="btn primary" :disabled="loading" @click="generate">
        {{ loading ? "生成中..." : "生成学习计划" }}
      </button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>

    <view class="card">
      <text class="card-title">我的计划</text>
      <view v-if="!plans.length" class="empty">暂无计划</view>
      <view v-for="plan in plans" :key="plan.id" class="plan-card">
        <view class="row space-between">
          <text class="plan-title">{{ plan.title }}</text>
          <view class="row gap">
            <text class="badge">{{ progress(plan) }}%</text>
            <text class="adjust-link" @click="adjustPlan(plan)">调整</text>
            <text class="delete-link" @click="deletePlan(plan)">删除</text>
          </view>
        </view>
        <text class="muted">{{ plan.start_date }} 至 {{ plan.end_date }}</text>
        <view class="plan-items">
          <view v-for="item in plan.items" :key="item.id" class="plan-item">
            <checkbox
              :checked="item.completed"
              color="#2563eb"
              @click="toggleItem(item)"
            />
            <text :class="item.completed ? 'muted done' : ''">{{ item.title }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";

import { api } from "@/api/request";
import type { PlanItem, StudyPlan } from "@/types";

const form = ref({
  major: "计算机科学与技术",
  grade: "大二",
  goal: "通过四级并掌握数据结构",
  daily_minutes: 90,
  weeks: 2,
  subjects: ["数据结构", "英语"],
});
const plans = ref<StudyPlan[]>([]);
const loading = ref(false);
const message = ref("");

function progress(plan: StudyPlan): number {
  if (!plan.items.length) return 0;
  return Math.round(
    (plan.items.filter((item) => item.completed).length / plan.items.length) * 100,
  );
}

async function load() {
  try {
    plans.value = await api.plans();
  } catch {
    plans.value = [];
  }
}

async function generate() {
  loading.value = true;
  message.value = "";
  try {
    await api.generatePlan(form.value);
    message.value = "计划生成成功";
    await load();
  } catch (err: any) {
    message.value = err?.detail || "生成失败";
  } finally {
    loading.value = false;
  }
}

async function toggleItem(item: PlanItem) {
  await api.completePlanItem(item.id, !item.completed);
  await load();
}

async function adjustPlan(plan: StudyPlan) {
  try {
    await api.adjustPlan(plan.id);
    message.value = "计划已按最新学习情况调整";
    await load();
  } catch (err: any) {
    message.value = err?.detail || "调整失败";
  }
}

function deletePlan(plan: StudyPlan) {
  uni.showModal({
    title: "删除计划",
    content: `确定删除「${plan.title}」吗？删除后无法恢复。`,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await api.deletePlan(plan.id);
        message.value = "计划已删除";
        await load();
      } catch (err: any) {
        message.value = err?.detail || "删除失败";
      }
    },
  });
}

onShow(load);
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.card-title {
  font-size: 30rpx;
  font-weight: 700;
  display: block;
  margin-bottom: 20rpx;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-bottom: 16rpx;
  color: #5b6b7a;
}

.row {
  display: flex;
  gap: 16rpx;
}

.half {
  flex: 1;
}

.input {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
}

.btn {
  width: 100%;
  border-radius: 12rpx;
  padding: 16rpx;
  font-size: 28rpx;
  font-weight: 600;
  margin-top: 8rpx;
}

.btn.primary {
  background: #2563eb;
  color: #fff;
}

.message {
  display: block;
  margin-top: 12rpx;
  color: #dc2626;
  font-size: 24rpx;
}

.empty {
  color: #5b6b7a;
  text-align: center;
  padding: 40rpx 0;
}

.plan-card {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
}

.plan-title {
  font-size: 28rpx;
  font-weight: 600;
}

.badge {
  background: #dcfce7;
  color: #15803d;
  border-radius: 999rpx;
  padding: 4rpx 14rpx;
  font-size: 22rpx;
}

.delete-link {
  color: #dc2626;
  font-size: 24rpx;
  padding: 4rpx 12rpx;
}

.adjust-link {
  color: #2563eb;
  font-size: 24rpx;
  padding: 4rpx 12rpx;
}

.muted {
  color: #5b6b7a;
  font-size: 22rpx;
}

.plan-items {
  margin-top: 14rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.plan-item {
  display: flex;
  align-items: center;
  gap: 10rpx;
  font-size: 24rpx;
}

.done {
  text-decoration: line-through;
}
</style>
