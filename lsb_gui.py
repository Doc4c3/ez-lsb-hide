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
        has_alpha = "A" in self.image.getbands()
        self.drop.config(
            text=f"{os.path.basename(path)}\n{self.image.width}x{self.image.height} "
                 f"({'带' if has_alpha else '无'}alpha)")
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
