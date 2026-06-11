"""H.264 SPS 宽高解析与 NAL 单元切分测试。

测试用 SPS 由内置的位流写入器按 H.264 规范（7.3.2.1.1）独立构造，
不依赖解析器自身的实现，可交叉验证解析逻辑。
"""

import unittest

from app.scrcpy import protocol


class BitWriter:
    """按 H.264 规范写入比特流（含 Exp-Golomb 编码）。"""

    def __init__(self):
        self.bits = []

    def write_bit(self, b: int) -> None:
        self.bits.append(b & 1)

    def write_bits(self, value: int, n: int) -> None:
        for i in range(n - 1, -1, -1):
            self.write_bit((value >> i) & 1)

    def write_ue(self, value: int) -> None:
        value += 1
        n = value.bit_length()
        self.write_bits(0, n - 1)
        self.write_bits(value, n)

    def to_bytes(self) -> bytes:
        # rbsp_stop_one_bit + 字节对齐
        bits = self.bits + [1]
        while len(bits) % 8:
            bits.append(0)
        out = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for b in bits[i : i + 8]:
                byte = (byte << 1) | b
            out.append(byte)
        return bytes(out)


def build_sps(
    pic_width_mbs: int,
    pic_height_map_units: int,
    frame_mbs_only: int = 1,
    profile_idc: int = 66,
    crop: tuple[int, int, int, int] | None = None,
    chroma_format_idc: int = 1,
) -> bytes:
    """构造一个完整 SPS NAL（含 NAL header 0x67，不含 start code）。"""
    w = BitWriter()
    w.write_bits(profile_idc, 8)
    w.write_bits(0, 8)  # constraint flags + reserved
    w.write_bits(31, 8)  # level_idc
    w.write_ue(0)  # seq_parameter_set_id
    if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
        w.write_ue(chroma_format_idc)
        if chroma_format_idc == 3:
            w.write_bit(0)  # separate_colour_plane_flag
        w.write_ue(0)  # bit_depth_luma_minus8
        w.write_ue(0)  # bit_depth_chroma_minus8
        w.write_bit(0)  # qpprime_y_zero_transform_bypass_flag
        w.write_bit(0)  # seq_scaling_matrix_present_flag
    w.write_ue(0)  # log2_max_frame_num_minus4
    w.write_ue(0)  # pic_order_cnt_type = 0
    w.write_ue(0)  # log2_max_pic_order_cnt_lsb_minus4
    w.write_ue(1)  # max_num_ref_frames
    w.write_bit(0)  # gaps_in_frame_num_value_allowed_flag
    w.write_ue(pic_width_mbs - 1)
    w.write_ue(pic_height_map_units - 1)
    w.write_bit(frame_mbs_only)
    if not frame_mbs_only:
        w.write_bit(0)  # mb_adaptive_frame_field_flag
    w.write_bit(1)  # direct_8x8_inference_flag
    if crop:
        w.write_bit(1)
        for c in crop:
            w.write_ue(c)
    else:
        w.write_bit(0)
    w.write_bit(0)  # vui_parameters_present_flag
    return b"\x67" + w.to_bytes()


class SpsDimensionTests(unittest.TestCase):
    def test_baseline_720p_no_crop(self):
        sps = build_sps(pic_width_mbs=80, pic_height_map_units=45)
        self.assertEqual(protocol.parse_sps_dimensions(sps), (1280, 720))

    def test_baseline_1080p_with_bottom_crop(self):
        # 1920x1088 编码尺寸，crop_bottom=4（4:2:0 下 CropUnitY=2 → 裁掉 8 像素）
        sps = build_sps(pic_width_mbs=120, pic_height_map_units=68, crop=(0, 0, 0, 4))
        self.assertEqual(protocol.parse_sps_dimensions(sps), (1920, 1080))

    def test_high_profile_portrait(self):
        # 竖屏 1080x1920（高 profile 走 chroma_format_idc 分支）
        sps = build_sps(pic_width_mbs=68, pic_height_map_units=120, profile_idc=100, crop=(0, 4, 0, 0))
        self.assertEqual(protocol.parse_sps_dimensions(sps), (1080, 1920))

    def test_invalid_sps_returns_none(self):
        self.assertIsNone(protocol.parse_sps_dimensions(b"\x67\x00"))

    def test_emulation_prevention_stripping(self):
        raw = b"\x00\x00\x03\x01\xab\x00\x00\x03\x00"
        self.assertEqual(
            protocol._strip_emulation_prevention(raw), b"\x00\x00\x01\xab\x00\x00\x00"
        )

    def test_extract_from_packet_with_multiple_nals(self):
        sps = build_sps(pic_width_mbs=80, pic_height_map_units=45)
        pps = b"\x68\xce\x3c\x80"
        idr = b"\x65\x88\x84\x00"
        packet = b"\x00\x00\x00\x01" + sps + b"\x00\x00\x00\x01" + pps + b"\x00\x00\x01" + idr
        self.assertEqual(protocol.extract_sps_dimensions(packet), (1280, 720))

    def test_extract_without_sps_returns_none(self):
        packet = b"\x00\x00\x00\x01\x68\xce\x3c\x80"
        self.assertIsNone(protocol.extract_sps_dimensions(packet))


class NalUnitBoundaryTests(unittest.TestCase):
    """混合 3/4 字节 start code 时单元边界必须按实际前缀长度回退。"""

    def test_mixed_start_code_lengths(self):
        nal1 = b"\x67\xaa\xbb"
        nal2 = b"\x68\xcc"
        nal3 = b"\x65\xdd\xee"
        # 4 字节 + 3 字节 + 4 字节 start code 混合
        data = b"\x00\x00\x00\x01" + nal1 + b"\x00\x00\x01" + nal2 + b"\x00\x00\x00\x01" + nal3
        units = protocol.parse_nal_units(data)

        self.assertEqual([t for t, _ in units], [protocol.NAL_SPS, protocol.NAL_PPS, protocol.NAL_IDR])
        # 单元数据含自身 start code，且不混入相邻单元的字节
        self.assertEqual(units[0][1], b"\x00\x00\x00\x01" + nal1)
        self.assertEqual(units[1][1], b"\x00\x00\x01" + nal2)
        self.assertEqual(units[2][1], b"\x00\x00\x00\x01" + nal3)

    def test_three_byte_start_code_followed_by_four_byte(self):
        nal1 = b"\x67\xaa"
        nal2 = b"\x65\xbb"
        data = b"\x00\x00\x01" + nal1 + b"\x00\x00\x00\x01" + nal2
        units = protocol.parse_nal_units(data)

        self.assertEqual(units[0][1], b"\x00\x00\x01" + nal1)
        self.assertEqual(units[1][1], b"\x00\x00\x00\x01" + nal2)


if __name__ == "__main__":
    unittest.main()
