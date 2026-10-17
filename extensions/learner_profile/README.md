# 本地学习者画像

扩展在常规聊天和精通路线请求中读取本机 `data/user/settings/learner_profile.md`，并将其作为上下文提供给模型。设置为空时，模型可在相关学习对话中提出一个可跳过的问题。

保存流程需要分开询问和同意。用户回答学习偏好本身不算存储许可；只有后续用户消息明确同意保存、画像事实可在当前对话的用户原文中找到时，工具才会追加一条内容。含糊、否定或缺少原文的调用会被拒绝。支持在明确询问“是否要保存该画像内容”后，对“好/可以”等简短肯定答复进行校验。重复内容不会追加。

画像数据只写入运行 DeepTutor 的本机设置目录；此发布包不含画像文件或真实示例。扩展不请求敏感个人信息。

## 安装

使用 DeepTutor 1.6.14 对应 Python 环境：

```powershell
python -m pip install -e extensions/learner_profile
```

安装扩展后重新启动 DeepTutor。测试使用临时设置目录和合成对话：

```powershell
python extensions/learner_profile/tests/test_learner_profile.py
```
