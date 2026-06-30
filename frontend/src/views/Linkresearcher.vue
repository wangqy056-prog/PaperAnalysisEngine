<template>
  <div v-loading="loading">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">📰 领研网</h2>
      <div>
        <span style="color:#909399; font-size:12px; margin-right:8px;">页数：</span>
        <el-input-number v-model="pages" :min="1" :max="5" size="small" style="margin-right: 8px;" />
        <el-button type="primary" @click="onRefresh" :loading="loading">
          <el-icon><Refresh /></el-icon> 强制刷新
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="cacheInfo"
      type="info"
      :closable="false"
      style="margin-bottom: 12px;"
    >
      {{ cacheInfo }}
    </el-alert>

    <el-empty v-if="!loading && !papers.length" description="暂无数据，点击刷新获取" />

    <el-row :gutter="16">
      <el-col v-for="(paper, idx) in papers" :key="idx" :xs="24" :sm="12" :md="8" style="margin-bottom: 16px;">
        <el-card shadow="hover" class="paper-card">
          <div class="paper-title">{{ paper.title }}</div>
          <div v-if="paper.en_title" class="paper-en-title">{{ paper.en_title }}</div>
          <div class="paper-meta">
            <el-tag size="small" type="info" v-if="paper.journal">{{ paper.journal }}</el-tag>
            <el-tag size="small" v-if="paper.date">{{ paper.date }}</el-tag>
          </div>
          <div class="paper-authors" v-if="paper.authors?.length">
            {{ Array.isArray(paper.authors) ? paper.authors.join(', ') : paper.authors }}
          </div>
          <div class="paper-tags" v-if="paper.tags?.length">
            <el-tag v-for="t in (Array.isArray(paper.tags) ? paper.tags : []).slice(0, 4)" :key="t" size="small" style="margin-right: 4px; margin-bottom: 4px;">
              {{ t }}
            </el-tag>
          </div>
          <div style="margin-top: 10px; text-align: right;">
            <el-button
              type="success"
              size="small"
              :loading="importingIdx === idx"
              :disabled="importedSet.has(idx)"
              @click="onImport(paper, idx)"
            >
              {{ importedSet.has(idx) ? '已导入' : '导入' }}
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { getLinkresearcher, importFromLinkresearcher } from '../api'

const loading = ref(false)
const papers = ref([])
const pages = ref(1)
const importingIdx = ref(-1)
const importedSet = ref(new Set())
const cacheInfo = ref('')

// 普通加载（命中缓存就返回）
const loadList = async () => {
  loading.value = true
  cacheInfo.value = ''
  try {
    const t0 = Date.now()
    const { data } = await getLinkresearcher(pages.value, false)
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1)
    papers.value = Array.isArray(data) ? data : (data.papers || [])
    importedSet.value = new Set()
    if (papers.value.length) {
      const latest = papers.value[0]?.date || '未知'
      cacheInfo.value = `已获取 ${papers.value.length} 篇论文（耗时 ${elapsed}s，最新日期 ${latest}）。领研网有 30 分钟缓存，点"强制刷新"获取最新内容。`
    }
  } catch (e) {
    ElMessage.error('加载领研网失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 强制刷新（清空缓存，重新启动浏览器抓取最新数据）
const onRefresh = async () => {
  loading.value = true
  cacheInfo.value = '正在启动浏览器抓取最新数据（约 5-10 秒）...'
  try {
    const t0 = Date.now()
    const { data } = await getLinkresearcher(pages.value, true)
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1)
    papers.value = Array.isArray(data) ? data : (data.papers || [])
    importedSet.value = new Set()
    if (papers.value.length) {
      const latest = papers.value[0]?.date || '未知'
      ElMessage.success(`已刷新获取 ${papers.value.length} 篇最新论文（耗时 ${elapsed}s）`)
      cacheInfo.value = `已获取 ${papers.value.length} 篇论文（耗时 ${elapsed}s，最新日期 ${latest}）。`
    } else {
      ElMessage.warning('未获取到论文')
    }
  } catch (e) {
    ElMessage.error('刷新失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onImport = async (paper, idx) => {
  importingIdx.value = idx
  try {
    await importFromLinkresearcher(paper.title)
    importedSet.value.add(idx)
    importedSet.value = new Set(importedSet.value)
    ElNotification({
      title: '导入成功',
      message: paper.title,
      type: 'success',
      duration: 3000,
    })
  } catch (e) {
    ElMessage.error('导入失败：' + (e.message || '未知错误'))
  } finally {
    importingIdx.value = -1
  }
}

onMounted(loadList)
</script>

<style scoped>
.paper-card {
  height: 100%;
}
.paper-title {
  font-weight: bold;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.paper-en-title {
  color: #909399;
  font-size: 12px;
  font-style: italic;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.paper-meta {
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.paper-authors {
  margin-top: 6px;
  color: #606266;
  font-size: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.paper-tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
}
</style>
