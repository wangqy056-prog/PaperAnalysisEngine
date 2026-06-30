<template>
  <div v-loading="loading">
    <h2>🏆 排行榜</h2>

    <el-card shadow="hover" style="margin-bottom: 20px">
      <el-form :inline="true">
        <el-form-item label="排序依据">
          <el-select v-model="sortBy" @change="applySort" style="width: 180px">
            <el-option label="综合评分" value="combo_value" />
            <el-option label="学术影响力" value="academic_impact" />
            <el-option label="商业潜力" value="commercial_potential" />
            <el-option label="创新指数" value="innovation_index" />
            <el-option label="可复现性" value="reproducibility" />
            <el-option label="引用数" value="citations" />
          </el-select>
        </el-form-item>
        <el-form-item label="Top 数量">
          <el-input-number v-model="limit" :min="10" :max="500" :step="10" @change="loadData" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="sortedList" stripe style="width: 100%" @row-click="goDetail">
      <el-table-column type="index" label="排名" width="100" align="center">
        <template #default="{ $index }">
          <el-tag v-if="$index < 3" :type="['danger', 'warning', 'success'][$index]" effect="dark">
            {{ ['🥇 第1', '🥈 第2', '🥉 第3'][$index] }}
          </el-tag>
          <span v-else>{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="280" show-overflow-tooltip />
      <el-table-column prop="authors" label="作者" width="180" show-overflow-tooltip>
        <template #default="{ row }">
          {{ Array.isArray(row.authors) ? row.authors.slice(0, 2).join(', ') : row.authors }}
        </template>
      </el-table-column>
      <el-table-column prop="journal" label="期刊" width="140" show-overflow-tooltip />
      <el-table-column prop="year" label="年份" width="80" align="center" />
      <el-table-column prop="citations" label="引用" width="80" align="center" sortable />
      <el-table-column prop="grade" label="评级" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.grade" :color="gradeColor(row.grade)" effect="dark">{{ row.grade }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :prop="sortBy" :label="sortLabel" width="120" align="center" sortable>
        <template #default="{ row }">
          <strong style="color:#409eff">{{ formatNum(row[sortBy]) }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="ID" width="120">
        <template #default="{ row }">
          <span style="font-family: monospace; font-size: 11px; color:#909399;">{{ (row.paper_id || row.id || '').substring(0, 12) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click.stop="goDetail(row)">详情</el-button>
          <el-button size="small" type="warning" link @click.stop="goAIAnalysis(row)">AI 分析</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getRatings } from '../api'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const sortBy = ref('combo_value')
const limit = ref(100)

const gradeColor = (grade) => {
  return { S: '#ff4444', A: '#ff8800', B: '#ffcc00', C: '#88cc00', D: '#88aaff', E: '#aaaaaa' }[grade] || '#aaa'
}

const sortLabel = computed(() => {
  return {
    combo_value: '综合',
    academic_impact: '学术',
    commercial_potential: '商业',
    innovation_index: '创新',
    reproducibility: '可复现',
    citations: '引用',
  }[sortBy.value] || ''
})

const sortedList = computed(() => {
  return [...list.value].sort((a, b) => (b[sortBy.value] ?? 0) - (a[sortBy.value] ?? 0))
})

const applySort = () => {}

const formatNum = (v) => {
  if (v === undefined || v === null) return '-'
  return typeof v === 'number' ? v.toFixed(1) : v
}

const goDetail = (row) => {
  const id = row.paper_id || row.id
  if (id) router.push(`/paper/${id}`)
}

const goAIAnalysis = (row) => {
  const id = row.paper_id || row.id
  if (id) router.push({ path: '/ai-analysis', query: { id } })
}

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await getRatings(limit.value)
    list.value = Array.isArray(data) ? data : (data.ratings || data.papers || [])
  } catch (e) {
    ElMessage.error('加载排行榜失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
