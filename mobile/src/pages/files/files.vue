<template>
  <view class="page">
    <view class="card">
      <text class="card-title">上传学习资料</text>
      <text class="muted">支持 PDF / Word / PPT / TXT</text>
      <button class="btn primary" @click="chooseFile">选择并上传</button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>

    <view class="card">
      <text class="card-title">我的文档</text>
      <view v-if="!documents.length" class="empty">还没有文档</view>
      <view v-for="doc in documents" :key="doc.id" class="doc-card">
        <text class="doc-name">{{ doc.filename }}</text>
        <text class="muted">{{ doc.file_type.toUpperCase() }} · {{ doc.chunks_count }} 片段</text>
        <view class="row gap">
          <button
            class="btn outline"
            :disabled="doc.status === 'parsed'"
            @click="parse(doc)"
          >
            解析
          </button>
          <button
            class="btn teal"
            :disabled="doc.status !== 'parsed'"
            @click="generate(doc)"
          >
            出题
          </button>
        </view>
      </view>
    </view>

    <view v-if="generated.length" class="card">
      <text class="card-title">生成的题目</text>
      <view v-for="question in generated" :key="question.id" class="question-card">
        <text class="stem">{{ question.stem }}</text>
        <text class="muted">{{ question.answer }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";

import { api, uploadDocument } from "@/api/request";
import type { DocumentItem, Question } from "@/types";

const documents = ref<DocumentItem[]>([]);
const generated = ref<Question[]>([]);
const message = ref("");

async function load() {
  try {
    documents.value = await api.documents();
  } catch {
    documents.value = [];
  }
}

function chooseFile() {
  uni.chooseMessageFile({
    count: 1,
    type: "file",
    extension: ["pdf", "docx", "pptx", "txt", "md"],
    success: async (res) => {
      const file = res.tempFiles[0];
      try {
        await uploadDocument(file.path);
        message.value = "上传成功";
        await load();
      } catch (err: any) {
        message.value = err?.detail || "上传失败";
      }
    },
  });
}

async function parse(doc: DocumentItem) {
  try {
    const result = await api.parseDocument(doc.id);
    message.value = `解析完成，共 ${result.chunks} 个片段`;
    await load();
  } catch (err: any) {
    message.value = err?.detail || "解析失败";
  }
}

async function generate(doc: DocumentItem) {
  try {
    generated.value = await api.fileQuestions(doc.id, {
      count: 5,
      question_type: "choice",
    });
    message.value = `已基于《${doc.filename}》生成题目`;
  } catch (err: any) {
    message.value = err?.detail || "出题失败";
  }
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

.muted {
  display: block;
  color: #5b6b7a;
  font-size: 24rpx;
  margin-bottom: 16rpx;
}

.btn {
  width: 100%;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
  font-weight: 600;
}

.btn.primary {
  background: #2563eb;
  color: #fff;
}

.btn.teal {
  background: #0f766e;
  color: #fff;
}

.btn.outline {
  border: 1px solid #2563eb;
  color: #2563eb;
  background: #fff;
  width: auto;
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

.doc-card {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
}

.doc-name {
  font-size: 28rpx;
  font-weight: 600;
  display: block;
  margin-bottom: 6rpx;
}

.row {
  display: flex;
  gap: 16rpx;
  margin-top: 12rpx;
}

.gap {
  gap: 12rpx;
}

.question-card {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
}

.stem {
  display: block;
  font-size: 28rpx;
  margin-bottom: 10rpx;
}
</style>
