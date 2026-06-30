<template>
  <div v-loading="loading">
    <h2>✨ AI 分析</h2>

    <el-card shadow="hover" style="margin-bottom: 20px">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="LLM 提供商">
          <el-select v-model="provider" @change="onSwitchProvider" style="width: 160px">
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="Groq" value="groq" />
            <el-option label="GLM" value="glm" />
          </el-select>
        </el-form-item>
        <el-form-item label="论文 ID">
          <el-input v-model="paperId" placeholder="输入论文 ID" style="width: 240px" @keyup.enter="onSearchPaper" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearchPaper">查询</el-button>
        </el-form-item>
      </el-form>

      <el-descriptions v-if="paperInfo" :column="2" border size="small" style="margin-top: 12px;">
        <el-descriptions-item label="标题" :span="2">{{ paperInfo.title }}</el-descriptions-item>
        <el-descriptions-item label="作者">{{ authorsText }}</el-descriptions-item>
        <el-descriptions-item label="年份">{{ paperInfo.year || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="hover" style="margin-bottom: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>选择分析类型</span>
          <span v-if="analyzing" style="font-size: 13px; color: #909399;">
            进度：{{ completedCount }} / {{ ANALYSIS_TYPES.length }}
          </span>
        </div>
      </template>
      <el-radio-group v-model="analysisType" size="default">
        <el-radio-button
          v-for="t in ANALYSIS_TYPES"
          :key="t.key"
          :label="t.key"
        >
          {{ t.label }}
          <span v-if="statusMap[t.key] === 'done'" style="color: #67c23a; margin-left: 4px;">✓</span>
          <span v-else-if="statusMap[t.key] === 'running'" style="color: #409eff; margin-left: 4px;">⟳</span>
          <span v-else-if="statusMap[t.key] === 'error'" style="color: #f56c6c; margin-left: 4px;">✗</span>
        </el-radio-button>
      </el-radio-group>
      <!-- 单独重试某个失败项的小按钮区 -->
      <div v-if="failedCount > 0" style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
        <span style="color: #909399; font-size: 12px; line-height: 28px;">单独重试：</span>
        <el-button
          v-for="t in ANALYSIS_TYPES.filter(x => statusMap[x.key] === 'error')"
          :key="'retry-' + t.key"
          size="small"
          type="warning"
          :loading="retryingKey === t.key"
          :disabled="analyzing"
          @click="onRetrySingle(t.key)"
        >
          {{ t.label }}
        </el-button>
      </div>
      <el-button
        type="primary"
        :loading="analyzing"
        :disabled="!paperId"
        @click="onAnalyze"
        style="margin-left: 12px;"
      >
        {{ analyzing ? '分析中...' : (hasAnyResult ? '重新分析全部' : '开始分析') }}
      </el-button>
      <el-button
        v-if="failedCount > 0"
        type="warning"
        :loading="retrying"
        :disabled="analyzing"
        @click="onRetryFailed"
      >
        重试失败项 ({{ failedCount }})
      </el-button>
      <el-button v-if="hasAnyResult" @click="onClear" :disabled="analyzing">清空结果</el-button>
    </el-card>

    <!-- 结果展示区：只切换显示，不重新调 API -->
    <el-card v-if="currentResult" shadow="hover">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>{{ currentTypeLabel }}</span>
          <el-button size="small" @click="copyResult">复制</el-button>
        </div>
      </template>
      <div class="markdown-body" v-html="currentRendered"></div>
    </el-card>
    <el-empty v-else-if="!analyzing && !paperId" description="输入论文 ID 后点击开始分析" />
    <el-empty v-else-if="!analyzing && !hasAnyResult" description="点击「开始分析」一次性生成所有分析结果" />
    <el-empty v-else-if="analyzing && statusMap[analysisType] !== 'done'" :description="`「${currentTypeLabel}」正在分析中...`" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import {
  aiSummary, aiTranslate, aiPlainSummary, aiAssess, aiFunctional, aiDeepAnalysis,
  aiSwitchProvider, aiGetProvider, getPaper,
} from '../api'

const route = useRoute()

// 所有分析类型定义（顺序即按钮顺序）
const ANALYSIS_TYPES = [
  { key: 'summary',    label: '📝 摘要',     fn: aiSummary },
  { key: 'translate',  label: '🌐 翻译',     fn: aiTranslate },
  { key: 'plain',      label: '🧒 通俗解读', fn: aiPlainSummary },
  { key: 'assess',     label: '⚖️ 价值评估', fn: aiAssess },
  { key: 'functional', label: '🛠️ 功能说明', fn: aiFunctional },
  { key: 'deep',       label: '🧠 综合分析', fn: aiDeepAnalysis },
]

const loading = ref(false)
const analyzing = ref(false)
const retrying = ref(false)
const retryingKey = ref('')
const provider = ref('deepseek')
const paperId = ref('')
const paperInfo = ref(null)
const analysisType = ref('summary')

// 结果缓存：key -> 结果文本
const results = ref({})
// 状态映射：key -> 'pending' | 'running' | 'done' | 'error'
const statusMap = ref({})

// 当前选中类型的结果
const currentResult = computed(() => results.value[analysisType.value] || '')
const currentTypeLabel = computed(() =>
  ANALYSIS_TYPES.find(t => t.key === analysisType.value)?.label || ''
)
const currentRendered = computed(() => {
  if (!currentResult.value) return ''
  try { return marked(currentResult.value) } catch { return currentResult.value }
})
const hasAnyResult = computed(() => Object.keys(results.value).length > 0)
const completedCount = computed(() =>
  Object.values(statusMap.value).filter(s => s === 'done' || s === 'error').length
)
const failedCount = computed(() =>
  Object.values(statusMap.value).filter(s => s === 'error').length
)

const authorsText = computed(() => {
  const a = paperInfo.value?.authors
  if (!a) return '-'
  if (Array.isArray(a)) return a.slice(0, 3).join(', ')
  return String(a)
})

const loadProvider = async () => {
  try {
    const { data } = await aiGetProvider()
    provider.value = data.provider || data.current || 'deepseek'
  } catch (e) { /* 静默 */ }
}

const onSwitchProvider = async () => {
  try {
    await aiSwitchProvider(provider.value)
    ElMessage.success(`已切换到 ${provider.value}`)
  } catch (e) {
    ElMessage.error('切换提供商失败')
  }
}

const onSearchPaper = async () => {
  if (!paperId.value) return
  loading.value = true
  try {
    const { data } = await getPaper(paperId.value)
    paperInfo.value = data
    // 只加载论文信息，不自动分析 —— 等用户手动点「开始分析」
  } catch (e) {
    ElMessage.error('查询论文失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onClear = () => {
  results.value = {}
  statusMap.value = {}
}

// 一次性并行生成所有 6 种分析；切换类型只切换显示，不重新调 API
const onAnalyze = async () => {
  if (!paperId.value) {
    ElMessage.warning('请先输入论文 ID')
    return
  }

  // 重置状态
  onClear()
  analyzing.value = true

  // 把所有类型标记为 running
  ANALYSIS_TYPES.forEach(t => { statusMap.value[t.key] = 'running' })

  // 提取结果的工具（兼容多种后端返回格式）
  const extract = (data) => {
    if (typeof data === 'string') return data
    return data.result || data.content || data.summary || data.translation
      || data.text || JSON.stringify(data, null, 2)
  }

  // 并行触发所有分析；每个独立完成、独立处理失败
  const tasks = ANALYSIS_TYPES.map(async ({ key, fn }) => {
    try {
      const { data } = await fn(paperId.value)
      results.value[key] = extract(data)
      statusMap.value[key] = 'done'
    } catch (e) {
      results.value[key] = `❌ 分析失败：${e.message || '未知错误'}`
      statusMap.value[key] = 'error'
    }
  })

  await Promise.allSettled(tasks)
  analyzing.value = false

  const ok = Object.values(statusMap.value).filter(s => s === 'done').length
  const fail = Object.values(statusMap.value).filter(s => s === 'error').length
  if (fail === 0) {
    ElMessage.success(`已完成全部 ${ok} 项分析，可点击上方按钮切换查看`)
  } else {
    ElMessage.warning(`完成 ${ok} 项，失败 ${fail} 项；可重新分析重试`)
  }
}

const copyResult = async () => {
  if (!currentResult.value) return
  try {
    await navigator.clipboard.writeText(currentResult.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 提取 LLM 返回结果的工具（兼容多种后端格式）
const extract = (data) => {
  if (typeof data === 'string') return data
  return data.result || data.content || data.summary || data.translation
    || data.text || JSON.stringify(data, null, 2)
}

// 执行单个分析任务（共享逻辑）
const runSingle = async (key, fn) => {
  try {
    const { data } = await fn(paperId.value)
    results.value = { ...results.value, [key]: extract(data) }
    statusMap.value = { ...statusMap.value, [key]: 'done' }
    return true
  } catch (e) {
    results.value = { ...results.value, [key]: `❌ 分析失败：${e.message || '未知错误'}` }
    statusMap.value = { ...statusMap.value, [key]: 'error' }
    return false
  }
}

// 单独重试某个失败项（不影响其他已成功的结果）
const onRetrySingle = async (key) => {
  if (!paperId.value || retryingKey.value) return
  retryingKey.value = key
  statusMap.value = { ...statusMap.value, [key]: 'running' }
  const t = ANALYSIS_TYPES.find(x => x.key === key)
  const ok = await runSingle(key, t.fn)
  retryingKey.value = ''
  if (ok) {
    ElMessage.success(`「${t.label}」分析成功`)
    analysisType.value = key  // 自动切换到刚重试成功的类型
  } else {
    ElMessage.error(`「${t.label}」仍然失败，请检查 LLM 配置`)
  }
}

// 批量重试所有失败项（不影响已成功的结果）
const onRetryFailed = async () => {
  if (!paperId.value || retrying) return
  const failedKeys = ANALYSIS_TYPES
    .filter(t => statusMap.value[t.key] === 'error')
    .map(t => t.key)
  if (failedKeys.length === 0) return

  retrying.value = true
  failedKeys.forEach(k => { statusMap.value[k] = 'running' })

  // 并行重试所有失败项
  const tasks = failedKeys.map(async (key) => {
    const t = ANALYSIS_TYPES.find(x => x.key === key)
    await runSingle(key, t.fn)
  })
  await Promise.allSettled(tasks)
  retrying.value = false

  const stillFail = ANALYSIS_TYPES.filter(t => statusMap.value[t.key] === 'error').length
  if (stillFail === 0) {
    ElMessage.success(`全部 ${failedKeys.length} 项失败已重试成功`)
  } else {
    ElMessage.warning(`重试完成，仍有 ${stillFail} 项失败`)
  }
}

onMounted(async () => {
  await loadProvider()
  // 从 URL 查询参数加载论文 ID（如 /ai-analysis?id=xxx）
  // 只加载论文信息，不自动分析；用户手动点「开始分析」一次性生成所有结果
  const id = route.query.id
  if (id) {
    paperId.value = String(id)
    await onSearchPaper()
  }
})
</script>

<style scoped>
.markdown-body {
  line-height: 1.7;
  color: #303133;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 6px;
}
.markdown-body :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
}
.markdown-body :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #ebeef5;
  padding: 8px;
}
</style>
