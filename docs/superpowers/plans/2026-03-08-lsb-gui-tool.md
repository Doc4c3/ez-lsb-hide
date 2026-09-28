# LSB 隐写注入 GUI 工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 Windows 桌面工具，把文本信息经 LSB 隐写注入 PNG/BMP 图片，最终交付 PyInstaller 单文件 exe。

**Architecture:** `lsb_core.py` 纯函数层负责位流打包/嵌入/提取（可单测），`lsb_gui.py` 负责 Tkinter 四元素界面并调用核心层。嵌入格式为 32 位大端长度头 + UTF-8 消息体，按行优先、通道 R→G→B→A、位平面升序逐 bit 写入。

**Tech Stack:** Python 3, Tkinter, Pillow, tkinterdnd2, PyInstaller, unittest（stdlib）

**Spec:** `docs/superpowers/specs/2026-03-08-lsb-gui-tool-design.md`

## Global Constraints

- 载体仅接受 PNG/BMP；输出一律 PNG。
- GUI 严格四元素：拖放框、信息输入框、通道+位平面选项排、「加密」按钮（容量/状态文字为辅助信息）。
- 默认勾选通道 R、G、B 与位平面 bit 0。
- 依赖仅限 requirements.txt 三项：pillow、tkinterdnd2、pyinstaller；测试用 stdlib unittest。
- 打包命令：`pyinstaller --onefile --noconsole --collect-all tkinterdnd2 --name LSBStegTool lsb_gui.py`。
- 工作目录：`C:\Users\12558\lsb-gui-tool`（已是 git 仓库）。

## Review Focus

1. 无 alpha 通道的 RGB 图片勾选了 A 通道 → 期望：A 被静默忽略，容量与写入只按有效通道计算，不崩溃。
2. 消息含中文/emoji（多字节 UTF-8）→ 期望：按字节数计容量并正确往返。
3. 消息恰好等于容量上限 → 期望：成功嵌入并可完整读回（不越位）。
4. 位平面选了非 0 平面（如 bit 7）→ 期望：仍能正确往返，图像明显失真也属正常。
5. 用户拖入 JPEG/GIF 等非无损格式 → 期望：GUI 拒绝并提示原因，不写任何文件。

---

### Task 1: 项目脚手架 + lsb_core 载荷与容量

**Files:**
- Create: `lsb-gui-tool/requirements.txt`
- Create: `lsb-gui-tool/lsb_core.py`
- Test: `lsb-gui-tool/tests/test_lsb_core.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `build_payload(message: str) -> list[int]`（MSB-first 位列表，含 32 位大端长度头）
  - `capacity_bits(img: PIL.Image.Image, channels: set[str], planes: set[int]) -> int`
  - `capacity_bytes(img, channels, planes) -> int`（`max(0, (capacity_bits - 32) // 8)`）
  - `_usable_channels(img, channels) -> list[str]`（按 RGBA 顺序过滤到图像实际波段）

- [ ] **Step 1: 写 requirements.txt 并安装依赖**

```
pillow
tkinterdnd2
pyinstaller
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: 写失败测试**

```python
# tests/test_lsb_core.py
import unittest
from PIL import Image
import lsb_core


class TestPayload(unittest.TestCase):
    def test_payload_header_and_bits(self):
        bits = lsb_core.build_payload("A")  # 'A' = 0x41
        self.assertEqual(len(bits), 32 + 8)
        # 长度头 1 → 前 31 bit 为 0，第 32 bit 为 1
        self.assertEqual(bits[:32], [0] * 31 + [1])
        # 0x41 = 01000001
        self.assertEqual(bits[32:], [0, 1, 0, 0, 0, 0, 0, 1])

    def test_payload_utf8_multibyte(self):
        bits = lsb_core.build_payload("中")  # 3 字节 UTF-8
        self.assertEqual(len(bits), 32 + 24)


class TestCapacity(unittest.TestCase):
    def test_rgb_capacity(self):
        img = Image.new("RGB", (4, 4))
        # 16 像素 * 3 通道 * 1 平面 = 48 bit；减 32 头 = 16 bit = 2 字节
        self.assertEqual(lsb_core.capacity_bytes(img, {"R", "G", "B"}, {0}), 2)

    def test_alpha_not_in_bands_is_ignored(self):
        img = Image.new("RGB", (4, 4))
        # 勾了 A 但图像无 alpha → 与只选 RGB 相同
        self.assertEqual(lsb_core.capacity_bytes(img, {"R", "G", "B", "A"}, {0}), 2)

    def test_rgba_multiple_planes(self):
        img = Image.new("RGBA", (4, 4))
        # 16 * 4 通道 * 2 平面 = 128 bit；减 32 = 96 bit = 12 字节
        self.assertEqual(lsb_core.capacity_bytes(img, {"R", "G", "B", "A"}, {0, 1}), 12)

    def test_no_channels_gives_zero(self):
        img = Image.new("RGB", (4, 4))
        self.assertEqual(lsb_core.capacity_bytes(img, set(), {0}), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m unittest discover -s tests -v`（工作目录 `lsb-gui-tool`）
Expected: FAIL —— `ModuleNotFoundError: No module named 'lsb_core'`

- [ ] **Step 4: 实现 lsb_core.py（载荷与容量部分）**

```python
# lsb_core.py
from PIL import Image

_CHANNEL_ORDER = ("R", "G", "B", "A")
_HEADER_BITS = 32


def build_payload(message: str) -> list[int]:
    data = message.encode("utf-8")
    blob = len(data).to_bytes(4, "big") + data
    bits = []
    for byte in blob:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _usable_channels(img: Image.Image, channels: set[str]) -> list[str]:
    bands = set(img.getbands())
    return [c for c in _CHANNEL_ORDER if c in channels and c in bands]


def capacity_bits(img: Image.Image, channels: set[str], planes: set[int]) -> int:
    usable = _usable_channels(img, channels)
    return img.width * img.height * len(usable) * len(planes)


def capacity_bytes(img: Image.Image, channels: set[str], planes: set[int]) -> int:
    return max(0, (capacity_bits(img, channels, planes) - _HEADER_BITS) // 8)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: PASS（4 个测试）

- [ ] **Step 6: Commit**

```bash
git add requirements.txt lsb_core.py tests/test_lsb_core.py
git commit -m "feat: lsb_core payload packing and capacity calculation"
```

### Task 2: lsb_core 嵌入与提取往返

**Files:**
- Modify: `lsb-gui-tool/lsb_core.py`
- Test: `lsb-gui-tool/tests/test_lsb_core.py`

**Interfaces:**
- Consumes: Task 1 的 `build_payload`, `_usable_channels`, `capacity_bits`, `_HEADER_BITS`
- Produces:
  - `embed(input_path: str, output_path: str, message: str, channels: set[str], planes: set[int]) -> None`，容量不足抛 `ValueError(f"容量不足：需要 {need} 字节，可用 {have} 字节")`
  - `extract(input_path: str, channels: set[str], planes: set[int]) -> str`（验证/测试用）
  - `_iter_write_order(img, channels, planes)` 生成 `(band_index, plane)` 写入顺序（内部，嵌入提取共用）

- [ ] **Step 1: 写失败测试（追加到 tests/test_lsb_core.py）**

```python
import os
import tempfile


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _make(self, mode, size=(8, 8), color=(120, 60, 30, 255)):
        path = os.path.join(self.dir, "in.png")
        Image.new(mode, size, color[: len(Image.new(mode, (1, 1)).getbands())]).save(path)
        return path

    def test_roundtrip_ascii(self):
        src = self._make("RGB")
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "hi", {"R", "G", "B"}, {0})
        self.assertEqual(lsb_core.extract(out, {"R", "G", "B"}, {0}), "hi")

    def test_roundtrip_chinese_emoji(self):
        src = self._make("RGB", size=(16, 16))
        out = os.path.join(self.dir, "out.png")
        msg = "你好，世界！🔐"
        lsb_core.embed(src, out, msg, {"R", "G", "B"}, {0})
        self.assertEqual(lsb_core.extract(out, {"R", "G", "B"}, {0}), msg)

    def test_exact_capacity_fits(self):
        src = self._make("RGB", size=(4, 4))  # 容量恰好 2 字节
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "hi", {"R", "G", "B"}, {0})
        self.assertEqual(lsb_core.extract(out, {"R", "G", "B"}, {0}), "hi")

    def test_overflow_raises(self):
        src = self._make("RGB", size=(4, 4))  # 容量 2 字节
        out = os.path.join(self.dir, "out.png")
        with self.assertRaises(ValueError) as ctx:
            lsb_core.embed(src, out, "hello", {"R", "G", "B"}, {0})
        self.assertIn("容量不足", str(ctx.exception))
        self.assertFalse(os.path.exists(out))

    def test_higher_plane_roundtrip(self):
        src = self._make("RGB", size=(8, 8))
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "ok", {"G"}, {7})
        self.assertEqual(lsb_core.extract(out, {"G"}, {7}), "ok")

    def test_alpha_channel_roundtrip(self):
        src = self._make("RGBA", size=(8, 8))
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "ok", {"A"}, {0})
        self.assertEqual(lsb_core.extract(out, {"A"}, {0}), "ok")

    def test_unselected_channels_untouched(self):
        src = self._make("RGB", size=(8, 8), color=(100, 100, 100, 255))
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "k", {"B"}, {0})
        before = Image.open(src).convert("RGB")
        after = Image.open(out).convert("RGB")
        for bp, ap in zip(before.getdata(), after.getdata()):
            self.assertEqual(bp[0], ap[0])  # R 不变
            self.assertEqual(bp[1], ap[1])  # G 不变
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL —— `AttributeError: module 'lsb_core' has no attribute 'embed'`

- [ ] **Step 3: 实现 embed / extract（追加到 lsb_core.py）**

```python
def _write_positions(img: Image.Image, channels: set[str], planes: set[int]):
    bands = img.getbands()
    band_idx = {name: i for i, name in enumerate(bands)}
    for c in _usable_channels(img, channels):
        for p in sorted(planes):
            yield band_idx[c], p


def embed(input_path: str, output_path: str, message: str,
          channels: set[str], planes: set[int]) -> None:
    img = Image.open(input_path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    bits = build_payload(message)
    total = capacity_bits(img, channels, planes)
    if len(bits) > total:
        need = (len(bits) - _HEADER_BITS) // 8
        have = max(0, (total - _HEADER_BITS) // 8)
        raise ValueError(f"容量不足：需要 {need} 字节，可用 {have} 字节")

    positions = list(_write_positions(img, channels, planes))
    px = img.load()
    it = iter(bits)
    for y in range(img.height):
        for x in range(img.width):
            pixel = list(px[x, y])
            for band, plane in positions:
                try:
                    bit = next(it)
                except StopIteration:
                    px[x, y] = tuple(pixel)
                    img.save(output_path, "PNG")
                    return
                mask = 1 << plane
                pixel[band] = (pixel[band] & ~mask) | (bit << plane)
            px[x, y] = tuple(pixel)
    img.save(output_path, "PNG")


def extract(input_path: str, channels: set[str], planes: set[int]) -> str:
    img = Image.open(input_path)
    positions = list(_write_positions(img, channels, planes))
    px = img.load()

    def bit_stream():
        for y in range(img.height):
            for x in range(img.width):
                pixel = px[x, y]
                for band, plane in positions:
                    yield (pixel[band] >> plane) & 1

    stream = bit_stream()
    header = 0
    for _ in range(_HEADER_BITS):
        header = (header << 1) | next(stream)
    data = bytearray()
    for _ in range(header):
        byte = 0
        for _ in range(8):
            byte = (byte << 1) | next(stream)
        data.append(byte)
    return bytes(data).decode("utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: PASS（Task 1 的 4 个 + 本任务 7 个）

- [ ] **Step 5: Commit**

```bash
git add lsb_core.py tests/test_lsb_core.py
git commit -m "feat: lsb embed/extract with capacity checks"
```

### Task 3: Tkinter GUI（四元素）

**Files:**
- Create: `lsb-gui-tool/lsb_gui.py`

**Interfaces:**
- Consumes: `lsb_core.embed`, `lsb_core.capacity_bytes`
- Produces: `main()` 启动 GUI；模块级无外部依赖注入需求

- [ ] **Step 1: 实现 lsb_gui.py**

```python
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

import lsb_core

CHANNELS = ("R", "G", "B", "A")
PLANES = tuple(range(8))
ACCEPT_EXT = (".png", ".bmp")


class LsbApp:
    def __init__(self, root):
        self.root = root
        root.title("LSB 隐写注入工具")
        root.geometry("560x520")
        self.image_path = None
        self.image = None

        # 元素 1：拖入文件方框（拖拽 + 点击浏览）
        self.drop = tk.Label(
            root, text="拖入 PNG / BMP 图片\n（或点击选择文件）",
            relief="sunken", bd=2, width=60, height=6, bg="#f0f0f0",
        )
        self.drop.pack(padx=12, pady=(12, 6), fill="x")
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self._on_drop)
        self.drop.bind("<Button-1>", lambda _e: self._browse())

        # 元素 2：信息输入口
        tk.Label(root, text="待嵌入信息（UTF-8）：").pack(anchor="w", padx=12)
        self.msg = tk.Text(root, height=5, width=60)
        self.msg.pack(padx=12, pady=(0, 6), fill="x")
        self.msg.bind("<KeyRelease>", lambda _e: self._update_capacity())

        # 元素 3：加密方式选项（stegsolve 风格：通道 × 位平面）
        opts = tk.Frame(root)
        opts.pack(padx=12, pady=4, fill="x")
        ch_frame = tk.LabelFrame(opts, text="通道")
        ch_frame.pack(side="left", padx=(0, 12))
        self.ch_vars = {}
        for c in CHANNELS:
            var = tk.IntVar(value=1 if c in "RGB" else 0)
            tk.Checkbutton(ch_frame, text=c, variable=var,
                           command=self._update_capacity).pack(side="left")
            self.ch_vars[c] = var
        pl_frame = tk.LabelFrame(opts, text="位平面 (bit)")
        pl_frame.pack(side="left")
        self.pl_vars = {}
        for p in PLANES:
            var = tk.IntVar(value=1 if p == 0 else 0)
            tk.Checkbutton(pl_frame, text=str(p), variable=var,
                           command=self._update_capacity).pack(side="left")
            self.pl_vars[p] = var

        self.capacity_lbl = tk.Label(root, text="容量：—", fg="#555")
        self.capacity_lbl.pack(anchor="w", padx=12)

        # 元素 4：「加密」按钮
        self.btn = tk.Button(root, text="加密", width=20, height=2,
                             command=self._encrypt)
        self.btn.pack(pady=10)

        self.status = tk.Label(root, text="就绪", fg="#333", anchor="w")
        self.status.pack(side="bottom", fill="x")

    # ---- 文件选择 ----
    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("无损图片", "*.png *.bmp")])
        if path:
            self._load(path)

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        self._load(path)

    def _load(self, path):
        if not path.lower().endswith(ACCEPT_EXT):
            messagebox.showerror(
                "格式不支持",
                "仅支持 PNG / BMP 无损格式。\nJPEG 等有损压缩会破坏 LSB 数据。")
            return
        try:
            self.image = Image.open(path)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))
            return
        self.image_path = path
        self.drop.config(
            text=f"{os.path.basename(path)}\n{self.image.width}x{self.image.height} "
                 f"({'A' if 'A' in self.image.getbands() else '无'}alpha)")
        self._update_capacity()

    # ---- 选项与容量 ----
    def _channels(self):
        return {c for c, v in self.ch_vars.items() if v.get()}

    def _planes(self):
        return {p for p, v in self.pl_vars.items() if v.get()}

    def _update_capacity(self):
        if not self.image:
            self.capacity_lbl.config(text="容量：—")
            return
        cap = lsb_core.capacity_bytes(self.image, self._channels(), self._planes())
        need = len(self.msg.get("1.0", "end-1c").encode("utf-8"))
        self.capacity_lbl.config(text=f"容量：{cap} 字节（当前信息 {need} 字节）")

    # ---- 加密 ----
    def _encrypt(self):
        if not self.image_path:
            messagebox.showwarning("缺少图片", "请先拖入一张 PNG / BMP 图片。")
            return
        message = self.msg.get("1.0", "end-1c")
        if not message:
            messagebox.showwarning("信息为空", "请输入待嵌入的信息。")
            return
        if not self._channels() or not self._planes():
            messagebox.showwarning("选项不完整", "请至少勾选一个通道和一个位平面。")
            return
        base = os.path.splitext(os.path.basename(self.image_path))[0]
        out = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile=f"{base}_steg.png",
            filetypes=[("PNG 图片", "*.png")])
        if not out:
            return
        try:
            lsb_core.embed(self.image_path, out, message,
                           self._channels(), self._planes())
        except ValueError as exc:
            messagebox.showerror("嵌入失败", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("嵌入失败", str(exc))
            return
        self.status.config(text=f"已输出：{out}")
        messagebox.showinfo("完成", f"嵌入成功！\n输出文件：{out}")


def main():
    root = TkinterDnD.Tk()
    LsbApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟运行 GUI（开发态）**

Run: `python lsb_gui.py`
Expected: 窗口出现，四元素齐全；拖入/点击加载 PNG 后容量文字更新；点「加密」输出 `*_steg.png`。

- [ ] **Step 3: 读回验证嵌入结果**

用 Task 2 的 `lsb_core.extract` 对 GUI 产出的 `*_steg.png` 读回，确认与输入信息一致：

```bash
python -c "import lsb_core; print(lsb_core.extract('test_steg.png', {'R','G','B'}, {0}))"
```

Expected: 打印出嵌入的原文。

- [ ] **Step 4: Commit**

```bash
git add lsb_gui.py
git commit -m "feat: tkinter GUI with drag-drop, plane options, encrypt button"
```

### Task 4: PyInstaller 打包 exe 并验收

**Files:**
- Create: `lsb-gui-tool/build_exe.bat`

**Interfaces:**
- Consumes: `lsb_gui.py`, `lsb_core.py`
- Produces: `dist/LSBStegTool.exe`

- [ ] **Step 1: 写 build_exe.bat**

```bat
@echo off
pyinstaller --onefile --noconsole --clean --collect-all tkinterdnd2 --name LSBStegTool lsb_gui.py
pause
```

- [ ] **Step 2: 执行打包**

Run: `pyinstaller --onefile --noconsole --clean --collect-all tkinterdnd2 --name LSBStegTool lsb_gui.py`（工作目录 `lsb-gui-tool`，超时给足 300s）
Expected: `dist/LSBStegTool.exe` 生成，构建日志无 ERROR。

- [ ] **Step 3: exe 端到端验收**

后台启动 exe：`./dist/LSBStegTool.exe`，确认窗口正常弹出（拖拽、选项、容量显示、嵌入保存、错误提示均按 Review Focus 与 spec 人工过一遍）。

- [ ] **Step 4: Commit**

```bash
git add build_exe.bat
git commit -m "build: pyinstaller onefile packaging script"
```
