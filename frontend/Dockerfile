# Paper Analysis Engine - Frontend Dockerfile
# 多阶段构建：先构建，再运行

# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app/frontend

# 复制 package.json 和 package-lock.json
COPY package.json package-lock.json ./

# 安装依赖（使用 npm ci 确保版本一致）
RUN npm ci

# 复制源代码
COPY . .

# 构建生产版本
RUN npm run build

# 运行阶段（使用 nginx 提供静态文件）
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

# 暴露端口
EXPOSE 80

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]
