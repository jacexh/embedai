# MCAP 预览 404 错误修复记录

## 问题描述

**错误信息**: `Failed to load resource: the server responded with a status of 404 (Not Found)`

**触发条件**: 直接访问 `/preview/:episodeId` 深层链接时，浏览器刷新或直接输入 URL 出现 404。

## 根本原因

1. **Nginx SPA Fallback 配置不完整**
   - 原配置只有基础的 `try_files`
   - 缺少对静态资源的专门处理
   - 没有处理 404 错误页面的回退

2. **测试覆盖不足**
   - E2E 测试只从根路径 `/` 开始，点击导航进入预览页
   - 缺少直接访问深层链接 (`/preview/:id`) 的测试
   - 没有验证 Nginx 的 SPA fallback 行为

## 修复内容

### 1. Nginx 配置修复

**文件**: `web/nginx.conf.template`

```nginx
# 新增：静态资源缓存配置
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    try_files $uri =404;
}

# 修改：SPA fallback
location / {
    try_files $uri $uri/ /index.html;
}

# 新增：404 错误处理，返回 index.html 让 React Router 处理
error_page 404 =200 /index.html;
```

### 2. 新增测试覆盖

#### E2E 深层链接测试

**文件**: `tests/e2e/test_mcap_preview.py`

新增测试类 `TestMcapPreviewDeepLinking`:
- `test_direct_access_to_preview_page`: 直接访问 `/preview/:id` 应返回 200
- `test_direct_access_to_nonexistent_episode`: 访问不存在的 episode ID
- `test_static_assets_are_not_spa_fallback`: 静态资源不应触发 SPA fallback
- `test_preview_page_with_special_chars_in_id`: 特殊字符安全测试

#### 前端单元测试

**文件**: `web/src/pages/__tests__/PreviewPage.test.tsx`

新增测试组 `deep linking`:
- `should extract episode ID from URL params`: 验证 URL 参数解析
- `should handle direct access to preview page`: 直接访问处理
- `should handle invalid episode ID format gracefully`: 无效 ID 处理
- `should preserve episode ID when navigating back`: 导航回退

## 为什么之前的测试没有发现这个问题

| 测试类型 | 测试路径 | 问题 |
|---------|---------|------|
| 单元测试 | 组件隔离测试 | 不涉及路由和 Nginx |
| E2E 测试 | `/` → 点击 → `/preview/:id` | 从根路径进入，Nginx 已加载 index.html |
| 集成测试 | API 测试 | 只测试后端接口 |

**缺失场景**: 浏览器直接访问 `http://localhost:3000/preview/xxx-xxx`

## 验证修复

```bash
# 1. 重新构建并启动服务
docker compose -f infra/docker-compose.prod.yml up -d --build web

# 2. 直接访问深层链接
curl -I http://localhost:3000/preview/some-episode-id
# 预期: HTTP/1.1 200 OK

# 3. 运行新的 E2E 测试
cd tests/e2e
pytest test_mcap_preview.py::TestMcapPreviewDeepLinking -v

# 4. 运行前端单元测试
cd web
npm test -- PreviewPage.test.tsx
```

## 预防措施

1. **所有 SPA 路由必须测试直接访问场景**
   - 不仅测试点击导航，还要测试直接 URL 访问
   - 包括刷新页面后的状态

2. **Nginx 配置变更必须验证**
   - 使用 `curl` 直接测试深层链接
   - 验证静态资源缓存行为
   - 检查 404 处理

3. **添加路由回归测试**
   ```python
   # E2E 测试模板
   async def test_spa_deep_link(self, client, path):
       """所有新路由必须添加此测试"""
       resp = await client.get(path)
       assert resp.status_code == 200
       assert "text/html" in resp.headers["content-type"]
   ```

## 相关文件变更

- `web/nginx.conf.template` - Nginx 配置
- `tests/e2e/test_mcap_preview.py` - E2E 深层链接测试
- `web/src/pages/__tests__/PreviewPage.test.tsx` - 前端深层链接测试
