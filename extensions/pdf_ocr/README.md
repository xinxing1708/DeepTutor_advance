# 本地扫描 PDF OCR

扩展使用本地 RapidOCR 处理扫描 PDF，支持逐页恢复、可搜索文本、阅读器/聊天来源读取，以及知识库解析中的物理页码映射。扫描文档可配置较长的隔离解析时间。OCR 逐页缓存与原 PDF 属于运行数据，不会写入代码目录。

## 安装与应用

在 DeepTutor 1.6.14 对应的 Python 环境中运行：

```powershell
python -m pip install -e extensions/pdf_ocr
python extensions/pdf_ocr/manage_integration.py check
```

确认文件状态均为 `original` 或 `patched` 后，停止 DeepTutor 并运行：

```powershell
python extensions/pdf_ocr/manage_integration.py apply
```

如要回退，先按使用中的其他扩展 README 处理共享宿主文件，再执行 `restore`。随后重新启动 DeepTutor。

## 测试

测试只使用合成页面、临时目录和伪造文件路径：

```powershell
python -m unittest discover -s extensions/pdf_ocr/tests -v
```

版本快照针对 1.6.14。扩展不会上传或打包本机 PDF、OCR 缓存或知识库索引。
