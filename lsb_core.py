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


def _normalize(img: Image.Image) -> Image.Image:
    if img.mode in ("RGB", "RGBA"):
        return img
    return img.convert("RGBA" if "A" in img.getbands() else "RGB")


def _usable_channels(img: Image.Image, channels: set[str]) -> list[str]:
    bands = set(img.getbands())
    return [c for c in _CHANNEL_ORDER if c in channels and c in bands]


def capacity_bits(img: Image.Image, channels: set[str], planes: set[int]) -> int:
    img = _normalize(img)
    usable = _usable_channels(img, channels)
    return img.width * img.height * len(usable) * len(planes)


def capacity_bytes(img: Image.Image, channels: set[str], planes: set[int]) -> int:
    return max(0, (capacity_bits(img, channels, planes) - _HEADER_BITS) // 8)


def _write_positions(img: Image.Image, channels: set[str], planes: set[int]):
    bands = img.getbands()
    band_idx = {name: i for i, name in enumerate(bands)}
    for c in _usable_channels(img, channels):
        for p in sorted(planes):
            yield band_idx[c], p


def embed(input_path: str, output_path: str, message: str,
          channels: set[str], planes: set[int]) -> None:
    img = _normalize(Image.open(input_path))
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
    try:
        header = 0
        for _ in range(_HEADER_BITS):
            header = (header << 1) | next(stream)
        max_bytes = max(0, (capacity_bits(img, channels, planes) - _HEADER_BITS) // 8)
        if header > max_bytes:
            raise ValueError("未检测到嵌入数据")
        data = bytearray()
        for _ in range(header):
            byte = 0
            for _ in range(8):
                byte = (byte << 1) | next(stream)
            data.append(byte)
    except StopIteration:
        raise ValueError("未检测到嵌入数据或数据不完整") from None
    return bytes(data).decode("utf-8")
