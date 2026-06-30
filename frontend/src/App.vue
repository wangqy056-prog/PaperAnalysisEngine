<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" style="background: #304156">
      <div style="padding: 20px; text-align: center; color: #fff; font-size: 18px; font-weight: bold;">
        📊 论文分析引擎
      </div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <template v-for="route in menuRoutes" :key="route.path">
          <el-menu-item :index="route.path">
            <el-icon><component :is="route.meta.icon" /></el-icon>
            <span>{{ route.meta.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
      <div style="position: absolute; bottom: 10px; left: 0; right: 0; text-align: center; color: #7a8ba6; font-size: 12px;">
        v0.4.0 · FastAPI + Vue
      </div>
    </el-aside>
    <el-main style="padding: 20px; overflow-y: auto;">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const menuRoutes = computed(() =>
  router.options.routes.filter(r => !r.meta?.hidden)
)
</script>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.el-aside {
  position: relative;
}
.el-menu {
  border-right: none !important;
}
</style>
