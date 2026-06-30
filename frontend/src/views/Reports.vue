<template>
  <div v-loading="loading">
    <h2>🖨️ 导出报告</h2>

    <el-card shadow="hover">
      <el-form :model="form" label-width="100px" style="max-width: 640px;">
        <el-form-item label="报告类型">
          <el-radio-group v-model="form.reportType">
            <el-radio label="statistics">统计报告</el-radio>
            <el-radio label="paper">论文报告</el-radio>
            <el-radio label="collection">收藏夹报告</el-radio>
            <el-radio label="search">搜索报告</el-radio>
            <el-radio label="recommendation">推荐报告</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="输出格式">
          <el-radio-group v-model="form.format">
            <el-radio label="markdown">Markdown</el-radio>
            <el-radio label="html">HTML</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.reportType === 'paper'" label="论文 ID">
          <el-input v-model="form.paperId" placeholder="输入论文 ID" style="width: 320px" />
        </el-form-item>
        <el-form-item v-if="form.reportType === 'collection'" label="收藏夹 ID">
          <el-input v-model="form.collectionId" placeholder="输入收藏夹 ID" style="width: 320px" />
        </el-form-item>
        <el-form-item v-if="form.reportType === 'search'" label="搜索关键词">
          <el-input v-model="form.query" placeholder="输入搜索关键词" style="width: 320px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="generating" @click="onGenerate">生成报告</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="result" shadow="hover" style="margin-top: 20px;">
      <template #header>生成结果</template>
      <el-alert title="报告生成成功" type="success" :closable="false" show-icon />
      <el-descriptions :column="1" border style="margin-top: 12px;">
        <el-descriptions-item label="文件路径">{{ result.file_path || result.path || '-' }}</el-descriptions-item>
        <el-descriptions-item label="文件大小">{{ formatSize(result.size) }}</el-descriptions-item>
        <el-descriptions-item label="生成时间">{{ result.generated_at || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 16px;">
        <el-button v-if="result.download_url || result.url" type="success" @click="download(result.download_url || result.url)">
          <el-icon><Download /></el-icon> 下载报告
        </el-button>
        <el-button v-if="result.preview" @click="previewVisible = true">预览内容</el-button>
      </div>
    </el-card>

    <el-dialog v-model="previewVisible" title="报告预览" width="80%" top="5vh">
      <pre style="max-height: 70vh; overflow: auto; background: #f5f7fa; padding: 12px; border-radius: 4px;">{{ result?.preview }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { generateReport } from '../api'

const loading = ref(false)
const generating = ref(false)
const previewVisible = ref(false)
const result = ref(null)

const form = reactive({
  reportType: 'statistics',
  format: 'markdown',
  paperId: '',
  collectionId: '',
  query: '',
})

const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

const onGenerate = async () => {
  if (form.reportType === 'paper' && !form.paperId.trim()) {
    ElMessage.warning('请输入论文 ID')
    return
  }
  if (form.reportType === 'collection' && !form.collectionId.trim()) {
    ElMessage.warning('请输入收藏夹 ID')
    return
  }
  if (form.reportType === 'search' && !form.query.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  generating.value = true
  result.value = null
  try {
    const { data } = await generateReport(
      form.reportType,
      form.format,
      form.paperId || null,
      form.collectionId || null,
      form.query || null,
    )
    result.value = data
    ElMessage.success('报告生成成功')
  } catch (e) {
    ElMessage.error('生成报告失败：' + (e.message || '未知错误'))
  } finally {
    generating.value = false
  }
}

const download = (url) => {
  const full = url.startsWith('http') ? url : `/api${url}`
  window.open(full, '_blank')
}
</script>
