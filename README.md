# 模型可用性测试工具

暖君 API 开放平台提供 · 模型可用性批量测试工具

## 功能

- **多提供商管理**：添加/编辑/删除 API 提供商（名称、地址、Key）
- **拉取模型**：从选中提供商拉取可用模型列表
- **并发测试**：多线程批量测试模型可用性，最多 6 个并发
- **实时统计**：自动统计成功/失败数量
- **配置持久化**：提供商信息自动保存，下次启动自动加载

## 使用方式

### Windows exe 版
下载 `dist/模型可用性测试工具.exe` 直接运行，无需安装 Python。

### 网页版
打开 `web版/index.html` 即可在浏览器中使用（配置存储在浏览器 localStorage）。

### Python 源码
```bash
pip install requests
python model_tester.py
```

## 技术栈
- 桌面端：Python 3 + tkinter + requests
- 网页版：原生 HTML/CSS/JavaScript
- 打包：PyInstaller
- 存储：JSON 文件（桌面端）/ localStorage（网页版）
