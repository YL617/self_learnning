# Stage 3 启动路径审计

审计基线：3e3303f。日期：2026-09-12。先审计后实施，生产代码未修改。

## 当前真实链路

```text
deploy/update -> compose up -> uvicorn -> lifespan create_all -> admin 初始化
              -> 已运行 backend 中人工 alembic upgrade head
background profile -> worker/beat（只依赖 MySQL/Redis 容器启动）
```

- `backend/app/main.py` 无条件 `Base.metadata.create_all(bind=engine)`，没有 APP_ENV 判断；开发、生产、TestClient lifespan 都执行。
- Dockerfile CMD 只运行 uvicorn，没有隐式迁移 entrypoint。
- deploy 脚本 `git pull --ff-only || true` 会吞掉拉取失败；随后先启动服务再 exec migration。
- update 脚本先构建和重启，再 exec migration；失败时新版应用可能已访问旧结构。
- Compose depends_on 只保证容器启动，不保证 Schema 就绪；没有 healthcheck。
- worker/beat 是 background profile，生产当前未启用；其 Celery 启动没有 revision guard。
- 容器自动重启会再次触发 create_all，但不会运行 Alembic。
- README 开发方式依赖自动建表；部署指南也保留首次启动后迁移的旧说明。
- `backend/tests/conftest.py` 独立对临时 SQLite 使用 drop_all/create_all，这是测试数据库生命周期，不等于生产迁移。
- 已有 migration/drift/adoption/cleanup 测试，但没有 `.github/workflows` Schema CI。

## 本轮选择

1. 应用所有环境启动均不自动建表；开发先执行 alembic upgrade head。
2. API 与 Celery 启动使用只读 revision guard，失败拒绝启动；测试 client fixture 显式替换该 guard，独立 guard/lifespan 测试不替换。
3. 部署脚本显式运行 migration，成功并通过 revision/drift 检查后才更新应用。
4. 正式接入 Fresh MySQL 8.4 CI；保留 SQLite 快速测试。
5. 不更改历史 migration，不新增业务 Schema，不执行生产切换。

## 独立风险审计

后端 requirements/requirements-ai 使用 >= 下限，无 Python lock，Docker 基础镜像为浮动 tag；同 commit 重建可能升级依赖。建议另行批准后冻结当前生产 Python 包版本及基础镜像 digest，增加可重复安装验证；本轮不擅自锁版本或升级包。

生产只读核验：backend Mounts=[]，/app/uploads 与 /app/vector_db 共 0 文件；容器重建会丢失未来未持久化文件。建议 Stage 3.x 明确维护窗口、停写、备份与校验后迁至共享命名卷（backend/worker 挂载一致），中长期单独评估对象存储。不直接变更卷配置。
