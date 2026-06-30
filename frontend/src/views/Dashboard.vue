<template>
  <div>
    <h2>📋 仪表盘</h2>
    <el-row :gutter="20" v-if="stats">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="论文总数" :value="stats.total_papers" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="平均评分" :value="stats.avg_score?.toFixed(1) || 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="最高评分" :value="stats.max_score?.toFixed(1) || 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="评级数" :value="stats.total_ratings" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px" v-if="stats">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>评级分布</template>
          <v-chart :option="gradeChart" style="height: 300px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>五维评分雷达</template>
          <v-chart :option="radarChart" style="height: 300px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>年份分布</template>
          <v-chart :option="yearChart" style="height: 300px" autoresize />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, RadarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { getStats, getRatings } from '../api'

use([CanvasRenderer, BarChart, RadarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const stats = ref(null)
const ratings = ref([])

onMounted(async () => {
  const [statsRes, ratingsRes] = await Promise.all([
    getStats(),
    getRatings(9999),
  ])
  stats.value = statsRes.data
  ratings.value = ratingsRes.data
})

const gradeChart = computed(() => {
  const dist = stats.value?.level_distribution || {}
  const colors = { S: '#ff4444', A: '#ff8800', B: '#ffcc00', C: '#88cc00', D: '#88aaff', E: '#aaaaaa' }
  const data = Object.entries(dist).map(([k, v]) => ({ value: v, name: k, itemStyle: { color: colors[k] || '#aaa' } }))
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.name) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data, name: '数量' }],
  }
})

const radarChart = computed(() => {
  if (!ratings.value.length) return {}
  const dims = ['academic_impact', 'commercial_potential', 'innovation_index', 'reproducibility', 'combo_value']
  const labels = ['学术影响力', '商业潜力', '创新指数', '可复现性', '组合价值']
  const avg = dims.map(d => {
    const vals = ratings.value.map(r => r[d] || 0)
    return vals.reduce((a, b) => a + b, 0) / vals.length
  })
  return {
    tooltip: {},
    radar: { indicator: labels.map(l => ({ name: l, max: 100 })), radius: 100 },
    series: [{
      type: 'radar',
      data: [{ value: avg, name: '平均', areaStyle: { color: 'rgba(0,128,255,0.2)' } }],
    }],
  }
})

const yearChart = computed(() => {
  if (!ratings.value.length) return {}
  const yearCount = {}
  ratings.value.forEach(r => {
    const y = r.year
    if (y) yearCount[y] = (yearCount[y] || 0) + 1
  })
  const sorted = Object.entries(yearCount).sort((a, b) => a[0] - b[0])
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: sorted.map(s => s[0]) },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: sorted.map(s => s[1]), name: '论文数', smooth: true, areaStyle: {} }],
  }
})
</script>
