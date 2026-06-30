<template>
  <div v-loading="loading">
    <h2>🌐 知识图谱可视化</h2>

    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>图谱配置</template>
          <el-form :model="form" label-width="90px" size="default">
            <el-form-item label="图谱类型">
              <el-select v-model="form.graphType" @change="loadGraph">
                <el-option label="领域共现" value="field_co_occurrence" />
                <el-option label="作者合作" value="author_collaboration" />
                <el-option label="关键词共现" value="keyword_co_occurrence" />
                <el-option label="论文相似" value="paper_similarity" />
                <el-option label="引用网络" value="citation_network" />
              </el-select>
            </el-form-item>
            <el-form-item label="节点数">
              <el-slider v-model="form.limit" :min="10" :max="300" :step="10" show-input @change="loadGraph" />
            </el-form-item>
            <el-form-item label="阈值">
              <el-slider v-model="form.threshold" :min="1" :max="20" :step="1" show-input @change="loadGraph" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadGraph" :loading="loading">重新生成</el-button>
            </el-form-item>
          </el-form>
          <el-divider />
          <div style="font-size: 12px; color: #909399;">
            <div>节点数：{{ stats.nodes }}</div>
            <div>边数：{{ stats.edges }}</div>
            <div>提示：节点大小=度数，可拖拽</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="16">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ graphTitle }}</span>
              <el-button size="small" @click="fitGraph">适应窗口</el-button>
            </div>
          </template>
          <div ref="networkContainer" style="height: 600px; background: #fafafa;"></div>
          <el-empty v-if="!stats.nodes" description="暂无图谱数据，请调整参数后重新生成" :image-size="60" style="margin-top: -300px; pointer-events: none;" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Network, DataSet } from 'vis-network/standalone'
import { getKnowledgeGraph } from '../api'

const loading = ref(false)
const networkContainer = ref(null)
let network = null

const form = reactive({
  graphType: 'field_co_occurrence',
  limit: 50,
  threshold: 1,
})

const stats = reactive({ nodes: 0, edges: 0 })

const graphTitleMap = {
  field_co_occurrence: '领域共现网络',
  author_collaboration: '作者合作网络',
  keyword_co_occurrence: '关键词共现网络',
  paper_similarity: '论文相似网络',
  citation_network: '引用网络',
}

const graphTitle = ref('领域共现网络')

const loadGraph = async () => {
  loading.value = true
  graphTitle.value = graphTitleMap[form.graphType] || '知识图谱'
  try {
    const { data } = await getKnowledgeGraph(form.graphType, form.limit, form.threshold)
    const nodesData = data.nodes || []
    const edgesData = data.edges || []

    const degreeMap = {}
    edgesData.forEach(e => {
      const s = e.from, t = e.to
      degreeMap[s] = (degreeMap[s] || 0) + 1
      degreeMap[t] = (degreeMap[t] || 0) + 1
    })

    const nodes = new DataSet(nodesData.map(n => ({
      id: n.id,
      label: n.label || n.name || String(n.id),
      value: (degreeMap[n.id] || 0) + 1,
      title: n.title || n.label || n.name || '',
      group: n.group || n.category,
      color: n.color || undefined,
    })))

    const edges = new DataSet(edgesData.map(e => ({
      from: e.from,
      to: e.to,
      value: e.value || e.weight || 1,
      title: e.label || e.title || '',
      width: Math.min((e.value || e.weight || 1), 5),
    })))

    stats.nodes = nodesData.length
    stats.edges = edgesData.length

    await nextTick()
    if (network) {
      network.destroy()
      network = null
    }
    if (networkContainer.value) {
      network = new Network(networkContainer.value, { nodes, edges }, {
        physics: { stabilization: { iterations: 200 }, barnesHut: { gravitationalConstant: -3000 } },
        nodes: {
          shape: 'dot',
          scaling: { min: 10, max: 50, label: { min: 8, max: 30 } },
          font: { size: 12, face: 'Tahoma' },
        },
        edges: {
          color: { opacity: 0.4 },
          smooth: { type: 'continuous' },
        },
        interaction: { hover: true, tooltipDelay: 200 },
      })
    }
    if (!nodesData.length) ElMessage.info('当前参数下没有图谱数据')
  } catch (e) {
    ElMessage.error('加载图谱失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const fitGraph = () => {
  if (network) network.fit({ animation: true })
}

onMounted(loadGraph)
onBeforeUnmount(() => {
  if (network) {
    network.destroy()
    network = null
  }
})
</script>
