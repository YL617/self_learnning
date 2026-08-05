<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">AI智学管家</text>
      <text class="hero-sub">规划 → 学习 → 练习 → 错题 → 激励</text>
    </view>

    <view class="stat-grid">
      <view class="stat-card">
        <text class="stat-value">{{ stats.total_minutes }}</text>
        <text class="stat-label">累计专注分钟</text>
      </view>
      <view class="stat-card">
        <text class="stat-value">{{ plans.length }}</text>
        <text class="stat-label">学习计划</text>
      </view>
      <view class="stat-card">
        <text class="stat-value">{{ questionCount }}</text>
        <text class="stat-label">练习题目</text>
      </view>
      <view class="stat-card">
        <text class="stat-value">{{ coinBalance }}</text>
        <text class="stat-label">智学币</text>
      </view>
    </view>

    <view class="card">
      <text class="card-title">快捷入口</text>
      <view class="menu-grid">
        <view class="menu-item" @click="go('/pages/plans/plans')">
          <text class="menu-name">学习计划</text>
          <text class="menu-desc">AI 生成个性化周计划</text>
        </view>
        <view class="menu-item" @click="go('/pages/questions/questions')">
          <text class="menu-name">智能练习</text>
          <text class="menu-desc">按知识点生成题目</text>
        </view>
        <view class="menu-item" @click="go('/pages/files/files')">
          <text class="menu-name">文件出题</text>
          <text class="menu-desc">上传资料自动出题</text>
        </view>
        <view class="menu-item" @click="go('/pages/focus/focus')">
          <text class="menu-name">专注模式</text>
          <text class="menu-desc">番茄钟 + 宠物成长</text>
        </view>
        <view class="menu-item" @click="go('/pages/wrong-book/wrong-book')">
          <text class="menu-name">错题本</text>
          <text class="menu-desc">举一反三巩固</text>
        </view>
        <view class="menu-item" @click="go('/pages/profile/profile')">
          <text class="menu-name">我的宠物</text>
          <text class="menu-desc">查看成长与金币</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";

import { api } from "@/api/request";

const stats = ref({ total_minutes: 0, session_count: 0, today_minutes: 0 });
const plans = ref<{ id: number; title: string }[]>([]);
const questionCount = ref(0);
const coinBalance = ref(0);

function go(url: string) {
  uni.navigateTo({ url });
}

async function load() {
  const results = await Promise.allSettled([
    api.stats(),
    api.plans(),
    api.questions(),
    api.transactions(),
  ]);
  if (results[0].status === "fulfilled") stats.value = results[0].value;
  if (results[1].status === "fulfilled") plans.value = results[1].value;
  if (results[2].status === "fulfilled") questionCount.value = results[2].value.length;
  if (results[3].status === "fulfilled") {
    coinBalance.value = results[3].value.reduce((sum, tx) => sum + tx.amount, 0);
  }
}

onShow(load);
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.hero {
  background: #2563eb;
  border-radius: 16rpx;
  padding: 32rpx;
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-bottom: 20rpx;
}

.hero-title {
  font-size: 40rpx;
  font-weight: 700;
}

.hero-sub {
  font-size: 24rpx;
  opacity: 0.9;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16rpx;
  margin-bottom: 20rpx;
}

.stat-card,
.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.stat-value {
  font-size: 36rpx;
  font-weight: 700;
}

.stat-label {
  color: #5b6b7a;
  font-size: 22rpx;
}

.card-title {
  font-size: 30rpx;
  font-weight: 700;
  display: block;
  margin-bottom: 20rpx;
}

.menu-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16rpx;
}

.menu-item {
  border: 1px solid #dde3e8;
  border-radius: 16rpx;
  padding: 22rpx;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.menu-name {
  font-size: 28rpx;
  font-weight: 600;
}

.menu-desc {
  color: #5b6b7a;
  font-size: 22rpx;
}
</style>
