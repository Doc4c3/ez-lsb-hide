import os
import tempfile
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

    def test_extract_clean_image_raises(self):
        # 纯白图：bit0 全为 1 → 头部读出 0xFFFFFFFF，远超容量 → 判定无嵌入数据
        src = os.path.join(self.dir, "clean.png")
        Image.new("RGB", (8, 8), (255, 255, 255)).save(src)
        with self.assertRaises(ValueError) as ctx:
            lsb_core.extract(src, {"R", "G", "B"}, {0})
        self.assertIn("未检测到嵌入数据", str(ctx.exception))

    def test_grayscale_capacity_matches_embed(self):
        # L 模式图：embed 会归一化为 RGB，capacity_bytes 应同样归一化
        src = self._make("RGB", size=(4, 4))
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "hi", {"R", "G", "B"}, {0})
        gray = os.path.join(self.dir, "gray.png")
        Image.new("L", (4, 4), 128).save(gray)
        with Image.open(gray) as img:
            cap = lsb_core.capacity_bytes(img, {"R", "G", "B"}, {0})
        # 归一化后应与 4x4 RGB 一致：2 字节，且确实能嵌入
        self.assertEqual(cap, 2)
        gout = os.path.join(self.dir, "gray_out.png")
        lsb_core.embed(gray, gout, "hi", {"R", "G", "B"}, {0})
        self.assertEqual(lsb_core.extract(gout, {"R", "G", "B"}, {0}), "hi")

    def test_unselected_channels_untouched(self):
        src = self._make("RGB", size=(8, 8), color=(100, 100, 100, 255))
        out = os.path.join(self.dir, "out.png")
        lsb_core.embed(src, out, "k", {"B"}, {0})
        before = Image.open(src).convert("RGB")
        after = Image.open(out).convert("RGB")
        for bp, ap in zip(before.getdata(), after.getdata()):
            self.assertEqual(bp[0], ap[0])  # R 不变
            self.assertEqual(bp[1], ap[1])  # G 不变


if __name__ == "__main__":
    unittest.main()
