# 跨会话连续学习

此扩展为当前 DeepTutor 工作区提供三项本地工具：

- `conversation_search` 与 `conversation_read`：按关键词检索会话，并读取选定消息分支核实内容。
- `question_review`：按原题顺序恢复错题解析队列，记录解析依据和用户理解确认；这些记录与原始答题成绩分开保存。
- 上下文提示说明错题队列状态、未作答题与独立复测要求。

查询发生在运行中的 DeepTutor 内。扩展从本机当前工作区读取会话，复盘数据库也保存在本机用户数据目录。此代码仓库不包含聊天数据库、复盘数据库、个人历史导入脚本或真实会话测试样本。

## 安装

```powershell
python -m pip install -e extensions/learning_continuity
```

重新启动 DeepTutor 后，可在支持扩展工具的普通聊天中使用。当前版本适配 DeepTutor 1.6.14；升级后先验证扩展协议与本地回归，不要对其他版本作假设。
