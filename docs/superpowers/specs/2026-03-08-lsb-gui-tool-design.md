# LSB 隐写注入 GUI 工具 — 设计文档

日期：2026-03-08

## 目标

开发一个 Windows 桌面工具，把文本信息通过 LSB（最低有效位）隐写注入无损图片，交付物为 **PyInstaller 打包的单文件 exe**。

## 用户与场景

CTF / 隐写术学习者。拖入图片 → 输入信息 → 选择通道与位平面 → 点「加密」→ 得到嵌入信息的 PNG，可用 stegsolve 打开对应位平面人工验证。

## 功能需求

1. **拖入文件方框**：支持拖拽（tkinterdnd2）与点击浏览双模式；只接受 PNG/BMP；显示文件名；拒绝其他格式并提示原因（JPEG 有损压缩会破坏 LSB）。
2. **信息输入口**：多行文本框，UTF-8 编码。
3. **加密方式选项**（复刻 stegsolve 平面选择）：
   - 通道复选框：R / G / B / A
   - 位平面复选框：bit 0 ~ bit 7
   - 默认勾选 R、G、B 和 bit 0（经典 LSB）
   - 选项或图片变化时实时显示当前可嵌入容量（字节）
4. **「加密」按钮**：执行嵌入，弹出保存对话框，输出 PNG（默认 `原名_steg.png`）。

严格只有这四个 UI 元素（外加容量提示文字与状态栏文字，属辅助信息不是独立控件）。

## 嵌入方案

- 载荷 = 32 位大端长度头（消息字节数）+ UTF-8 消息字节。
- 逐 bit 顺序写入：按行优先遍历像素，每个像素按 R→G→B→A 顺序处理选中通道，将该通道指定位平面的 bit 替换为载荷 bit。
- 输出强制保存为 PNG（无损），即使用户拖入 BMP。
- 多个位平面被选中时，容量与写入顺序按 bit0→bit7 逐平面处理（每像素每通道先写最低选中平面）。

## 错误处理

- 未选图片 / 消息为空 / 未选任何通道或位平面：按钮置灰或点击时提示。
- 载荷超过容量：明确报错，显示当前容量与所需字节数。
- 非 PNG/BMP：拒绝并说明只支持无损格式。
- 含 alpha 通道的图片未勾 A 通道时，A 通道原样保留。

## 技术栈

- Python 3 + Tkinter（GUI）
- Pillow（图像读写）
- tkinterdnd2（拖拽）
- PyInstaller（打包，`--onefile --noconsole`，依赖随包打入）

## 项目结构

```
lsb-gui-tool/
├── lsb_core.py       # 纯函数：载荷打包、容量计算、嵌入、测试用提取
├── lsb_gui.py        # Tkinter GUI（四元素），调用 lsb_core
├── tests/test_lsb_core.py  # unittest 单元测试
├── requirements.txt  # pillow, tkinterdnd2, pyinstaller
├── build_exe.bat     # 打包脚本
└── docs/superpowers/specs/2026-03-08-lsb-gui-tool-design.md
```

## 验证

1. 单元级自检脚本：嵌入后用 Pillow 读回像素，比对选定位平面上的 bit 流与期望载荷一致。
2. 端到端：打包出 exe，拖入测试 PNG，嵌入中文消息，用读回脚本验证；可用 stegsolve 人工确认位平面。
3. 容量边界测试：超长消息报错；恰好装满成功。
