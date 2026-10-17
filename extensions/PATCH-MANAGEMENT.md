# 版本化宿主补丁

部分扩展需要将已审查的文件补丁应用到 DeepTutor 安装包。每个组件保留 `upstream-1.6.14`、`patched-1.6.14` 快照及 `integration-manifest-1.6.14.json` 清单；`integration_manager.py` 会先比对 SHA-256，再执行检查、应用或恢复。

从仓库根目录运行，使用目标安装环境中的 Python：

```powershell
python extensions/<component>/manage_integration.py check
python extensions/<component>/manage_integration.py apply
python extensions/<component>/manage_integration.py restore
```

对前端资源，使用 `extensions/chat_continuation/manage_frontend.py`。应用前先停止正在运行的 DeepTutor。使用隔离副本验证时，通过 `--target <package-or-frontend-directory>` 指定目标。

仅将清单匹配的补丁用于 1.6.14。检查报告未知文件或没有该版本清单时，停止并重新审查新版宿主代码；不要强行覆盖。多个扩展共享文件时，应遵循其 README 的应用与回退顺序。

这些管理器按文件校验并写入，不提供跨多个文件的事务回滚。升级前应自行备份目标安装。
