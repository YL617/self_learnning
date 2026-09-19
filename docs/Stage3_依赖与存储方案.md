# Stage 3 依赖与存储方案

依赖冻结已在 Stage 3.1 实施；volume 迁移仍未执行，保留为独立 Stage 3.x。

## 依赖构建

`backend/requirements.txt` 与 `requirements-ai.txt` 继续作为人工维护的直接依赖声明。生产构建通过 `constraints-prod.lock` 固定全部 152 个运行依赖版本；该文件与线上运行镜像的 `pip freeze --all` 逐项核对，仅排除不属于应用依赖树的 pip。`setuptools` 虽由基础镜像预装，但也被当前运行依赖要求，因此同样固定为线上已验证的 84.0.0。Dockerfile 通过 constraints 安装后执行 `pip check`。

生产镜像审计值：Python 3.12.14、FastAPI 0.141.1、SQLAlchemy 2.0.52、Alembic 1.19.1、Pydantic 2.13.5、Celery 5.6.3、Uvicorn 0.52.4、PyMySQL 1.2.0；关键传递依赖包括 Starlette 1.6.0、pydantic-core 2.46.5、Kombu 5.6.2、Billiard 4.2.4、httpcore 1.0.9。线上 `pip check` 通过。

基础镜像固定为：

`python:3.12.14-slim-trixie@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`

线上应用镜像的前四个 RootFS layer 与该 digest 的四层完全相同，因此该值来自实际层比对。构建时还写入 OCI source revision 和 constraints SHA-256 标签，发布脚本从当前 Git commit 与 lock 文件计算并传入，便于追溯候选镜像。

当前冻结是“版本级可重复”：基础镜像 digest 与 Python 包版本固定，没有趁机升级依赖。constraints 尚未附每个 wheel 的文件 hash，因此不能宣称供应文件字节级完全锁定；候选镜像必须记录最终 image ID，并由 CI 与隔离验证共同作为 Cutover 门槛。`backend/.dockerignore` 继续阻止 `.env`、虚拟环境、数据库、上传文件和日志进入构建上下文。

`requirements-dev.txt` 使用同一 constraints 固定核心依赖，并固定 pytest/ruff 版本；它不安装 `requirements-ai.txt`。这是既有测试边界：全新容器安装 Chroma 后，文件解析测试会触发默认嵌入模型冷下载，使 CI 依赖外部模型服务。完整生产镜像仍安装并锁定 AI 依赖，候选镜像通过实际构建、`pip check`、应用启动与健康检查验证；AI/RAG 的离线模型缓存测试应在独立任务中显式准备模型，而不能混入 Schema CI。

## uploads/vector_db

只读核验结果：backend Mounts=[]，/app/uploads 与 /app/vector_db 当前共 0 文件。目录内容在容器可写层，删除或替换容器后可能丢失。零文件仅代表核验时刻，不能据此保证下一次部署仍为空。

建议作为独立 Stage 3.x：

1. 明确维护窗口，停止 backend 与文件相关 worker 写入。
2. 备份目录、记录文件数量与逐文件哈希；不把业务文件提交 Git。
3. 为 uploads 与 vector_db 建立两个命名卷，复制已有文件并校验。backend 与涉及文件的 worker 挂载同一来源和路径。
4. 确认权限、数据库 storage_path 与挂载路径一致，再启动服务。
5. 保留旧容器或目录备份，验证文件下载、头像、解析与检索；失败时在停写条件下恢复旧挂载。

单机 Compose 近期更适合命名卷配合独立备份；bind mount 便于主机直接检查但需管好目录权限。OSS 适合作为后续原始文件存储方案，不能把正在使用的 Chroma 数据目录直接当普通对象存储挂载。

Stage 3 当前仅实现保守检查：发现未被持久化卷覆盖的 runtime 文件即拒绝替换容器。既不自动建卷，也不自动迁移文件。

## 备份脚本既有限制

现有 backup_mysql.sh 固定使用 /opt/ai-study 与每日文件名，未采用本轮独立的原子临时文件改造。本轮保留生产脚本内容与既有权限状态，使用其退出码作为部署门槛。非标准 APP_DIR 需提供经审核的 BACKUP_SCRIPT。更完整的备份可恢复性、同日版本保留和原子落盘可独立改进，不能由“退出码为零”推断已经做过真实恢复演练。
