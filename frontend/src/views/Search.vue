<template>
  <div v-loading="loading">
    <h2>🔍 搜索论文</h2>

    <el-card shadow="hover" style="margin-bottom: 20px">
      <el-form :inline="true" :model="form" @submit.prevent>
        <el-form-item label="关键词">
          <el-input
            v-model="form.q"
            placeholder="输入标题 / 作者 / 关键词"
            clearable
            style="width: 320px"
            @keyup.enter="onLocalSearch"
          />
        </el-form-item>
        <el-form-item label="年份从">
          <el-input-number v-model="form.yearFrom" :min="1900" :max="2099" controls-position="right" />
        </el-form-item>
        <el-form-item label="最低引用">
          <el-input-number v-model="form.minCitations" :min="0" :step="10" controls-position="right" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.limit" :min="1" :max="200" controls-position="right" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onLocalSearch">本地搜索</el-button>
          <el-button type="success" @click="onOnlineSearch">在线搜索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div v-if="searchMode" style="margin-bottom: 12px; color: #909399;">
      <el-tag :type="searchMode === 'online' ? 'success' : 'primary'">
        {{ searchMode === 'online' ? '在线搜索结果' : '本地搜索结果' }}
      </el-tag>
      <span style="margin-left: 10px;">共 {{ results.length }} 条</span>
    </div>

    <el-empty v-if="!loading && !results.length" description="暂无搜索结果，请输入关键词搜索" />

    <el-row :gutter="16">
      <el-col v-for="paper in results" :key="paper.paper_id || paper.title" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom: 16px;">
        <el-card shadow="hover" class="paper-card" @click="goDetail(paper)">
          <div class="paper-title">{{ paper.title }}</div>
          <div class="paper-meta">
            <span v-if="paper.authors?.length">{{ paper.authors.slice(0, 3).join(', ') }}{{ paper.authors.length > 3 ? ' 等' : '' }}</span>
          </div>
          <div class="paper-meta">
            <el-tag size="small" type="info" v-if="paper.journal">{{ paper.journal }}</el-tag>
            <el-tag size="small" v-if="paper.year">{{ paper.year }}</el-tag>
          </div>
          <div class="paper-meta">
            <el-tag size="small" type="warning">引用 {{ paper.citations ?? 0 }}</el-tag>
            <el-tag v-if="paper.grade" :color="gradeColor(paper.grade)" effect="dark" size="small">
              {{ paper.grade }}
            </el-tag>
          </div>
          <div class="paper-footer">
            <span class="paper-id">ID: {{ (paper.paper_id || paper.id || '').substring(0, 16) }}</span>
            <el-button size="small" type="warning" link @click.stop="goAIAnalysis(paper)">AI 分析</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { searchPapers, searchOnline } from '../api'

const router = useRouter()
const loading = ref(false)
const results = ref([])
const searchMode = ref('')

const form = reactive({
  q: '',
  yearFrom: 1990,
  minCitations: 0,
  limit: 20,
})

const gradeColor = (grade) => {
  return { S: '#ff4444', A: '#ff8800', B: '#ffcc00', C: '#88cc00', D: '#88aaff', E: '#aaaaaa' }[grade] || '#aaa'
}

const goDetail = (paper) => {
  const id = paper.paper_id || paper.id
  if (id) router.push(`/paper/${id}`)
}

const goAIAnalysis = (paper) => {
  const id = paper.paper_id || paper.id
  if (id) router.push({ path: '/ai-analysis', query: { id } })
}

const onLocalSearch = async () => {
  if (!form.q.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  loading.value = true
  try {
    const { data } = await searchPapers(form.q, form.limit, form.yearFrom, form.minCitations)
    results.value = Array.isArray(data) ? data : (data.papers || [])
    searchMode.value = 'local'
    if (!results.value.length) ElMessage.info('本地未找到匹配论文')
  } catch (e) {
    ElMessage.error('本地搜索失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onOnlineSearch = async () => {
  if (!form.q.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  loading.value = true
  try {
    const { data } = await searchOnline(form.q, form.limit)
    results.value = Array.isArray(data) ? data : (data.papers || [])
    searchMode.value = 'online'
    if (!results.value.length) ElMessage.info('在线未找到匹配论文')
  } catch (e) {
    ElMessage.error('在线搜索失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.paper-card {
  cursor: pointer;
  height: 100%;
  transition: transform 0.2s;
}
.paper-card:hover {
  transform: translateY(-3px);
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
.paper-meta {
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  color: #606266;
  font-size: 12px;
}
.paper-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.paper-id {
  font-family: monospace;
  font-size: 11px;
  color: #909399;
}
</style>
