"""scrcpy 协议解析：H.264 NAL 单元解析与控制指令编码。

H.264 NAL 解析：
- 从 scrcpy-server 的 video socket 接收的是带 frame meta 的 H.264 裸流
- 每个数据包可能包含多个 NAL 单元（SPS/PPS/IDR/非IDR）
- 前端 WebCodecs 需要区分 key frame 和 delta frame

控制指令编码：
- scrcpy 控制协议使用大端序二进制格式
- 每个指令以 1 字节 type 开头，后跟指令特定数据
"""

import struct

# ─── H.264 NAL 类型常量 ───

NAL_TYPE_MASK = 0x1F

NAL_SLICE = 1  # 非 IDR 切片（P/B 帧）
NAL_IDR = 5  # IDR 关键帧
NAL_SEI = 6  # 补充增强信息
NAL_SPS = 7  # 序列参数集
NAL_PPS = 8  # 图像参数集
NAL_AUD = 9  # 访问单元分隔符

# ─── scrcpy 控制指令类型 ───

CONTROL_TYPE_INJECT_KEYCODE = 0
CONTROL_TYPE_INJECT_TEXT = 1
CONTROL_TYPE_INJECT_TOUCH = 2
CONTROL_TYPE_INJECT_SCROLL = 3
CONTROL_TYPE_BACK_OR_SCREEN_ON = 4
CONTROL_TYPE_EXPAND_NOTIFICATION_PANEL = 5
CONTROL_TYPE_EXPAND_SETTINGS_PANEL = 6
CONTROL_TYPE_COLLAPSE_PANELS = 7
CONTROL_TYPE_GET_CLIPBOARD = 8
CONTROL_TYPE_SET_CLIPBOARD = 9
CONTROL_TYPE_SET_SCREEN_POWER_MODE = 10
CONTROL_TYPE_ROTATE_DEVICE = 11

# 触控动作
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2

# Android KeyEvent
KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_VOLUME_UP = 24
KEYCODE_VOLUME_DOWN = 25
KEYCODE_POWER = 26
KEYCODE_TAB = 61
KEYCODE_SPACE = 62
KEYCODE_ENTER = 66
KEYCODE_DEL = 67  # Backspace
KEYCODE_ESCAPE = 111
KEYCODE_FORWARD_DEL = 112  # Delete
KEYCODE_APP_SWITCH = 187

# Android MetaState
META_SHIFT_ON = 0x01
META_ALT_ON = 0x02
META_CTRL_ON = 0x1000

# 剪贴板 copy_key
COPY_KEY_NONE = 0
COPY_KEY_COPY = 1
COPY_KEY_CUT = 2


def parse_nal_units(data: bytes) -> list[tuple[int, bytes]]:
    """解析 H.264 数据包中的 NAL 单元。

    Args:
        data: 原始 H.264 数据（可能包含多个 NAL 单元）

    Returns:
        [(nal_type, nal_data), ...] 列表
    """
    units = []
    # 查找 start code，记录 (payload 起始位置, start code 前缀起始位置)
    # 统一按 0x000001 扫描：若前一字节为 0x00 则实际是 4 字节 start code
    i = 0
    marks: list[tuple[int, int]] = []
    while i + 3 <= len(data):
        if data[i : i + 3] == b"\x00\x00\x01":
            prefix_start = i - 1 if i >= 1 and data[i - 1] == 0 else i
            marks.append((i + 3, prefix_start))
            i += 3
        else:
            i += 1

    if not marks:
        # 没有 start code，整个数据作为一个 NAL
        if len(data) > 0:
            nal_type = data[0] & NAL_TYPE_MASK
            units.append((nal_type, data))
        return units

    for idx, (payload_start, prefix_start) in enumerate(marks):
        # 当前单元结束于下一个 start code 的前缀起始处（按实际前缀长度回退）
        end = marks[idx + 1][1] if idx + 1 < len(marks) else len(data)
        nal_data = data[payload_start:end]
        if len(nal_data) > 0:
            nal_type = nal_data[0] & NAL_TYPE_MASK
            units.append((nal_type, data[prefix_start:end]))

    return units


# ─── SPS 宽高解析（设备旋转/分辨率变化时更新 screen_size 用） ───

# H.264 规范中携带 chroma_format_idc 等扩展字段的 profile_idc 集合
_HIGH_PROFILE_IDCS = frozenset({100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135})


class _BitReader:
    """大端序按位读取器，用于解析 Exp-Golomb 编码的 SPS 字段。"""

    def __init__(self, data: bytes):
        self._data = data
        self._bit_pos = 0

    def read_bit(self) -> int:
        byte_idx, bit_idx = divmod(self._bit_pos, 8)
        if byte_idx >= len(self._data):
            raise ValueError("SPS 比特流越界")
        self._bit_pos += 1
        return (self._data[byte_idx] >> (7 - bit_idx)) & 1

    def read_bits(self, n: int) -> int:
        value = 0
        for _ in range(n):
            value = (value << 1) | self.read_bit()
        return value

    def read_ue(self) -> int:
        """读取无符号 Exp-Golomb 编码值。"""
        zeros = 0
        while self.read_bit() == 0:
            zeros += 1
            if zeros > 31:
                raise ValueError("非法的 Exp-Golomb 编码")
        if zeros == 0:
            return 0
        return (1 << zeros) - 1 + self.read_bits(zeros)

    def read_se(self) -> int:
        """读取有符号 Exp-Golomb 编码值。"""
        ue = self.read_ue()
        return (ue + 1) // 2 if ue % 2 else -(ue // 2)


def _strip_emulation_prevention(data: bytes) -> bytes:
    """剥离 NAL 中的防竞争字节（00 00 03 → 00 00），得到 RBSP。"""
    out = bytearray()
    i = 0
    while i < len(data):
        if i + 2 < len(data) and data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 3:
            out += data[i : i + 2]
            i += 3
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def _skip_scaling_list(reader: _BitReader, size: int) -> None:
    """跳过 SPS 中的 scaling list（仅消费比特，不使用内容）。"""
    last_scale, next_scale = 8, 8
    for _ in range(size):
        if next_scale != 0:
            next_scale = (last_scale + reader.read_se() + 256) % 256
        last_scale = next_scale if next_scale != 0 else last_scale


def _strip_start_code(nal: bytes) -> bytes:
    """剥离 NAL 前缀的 start code（如有）。"""
    if nal.startswith(b"\x00\x00\x00\x01"):
        return nal[4:]
    if nal.startswith(b"\x00\x00\x01"):
        return nal[3:]
    return nal


def parse_sps_dimensions(nal: bytes) -> tuple[int, int] | None:
    """从 SPS NAL 单元解析视频宽高。

    Args:
        nal: 不含 start code 的 SPS NAL（首字节为 NAL header）

    Returns:
        (width, height)，解析失败返回 None
    """
    try:
        reader = _BitReader(_strip_emulation_prevention(nal[1:]))
        profile_idc = reader.read_bits(8)
        reader.read_bits(8)  # constraint flags + reserved
        reader.read_bits(8)  # level_idc
        reader.read_ue()  # seq_parameter_set_id

        chroma_format_idc = 1
        if profile_idc in _HIGH_PROFILE_IDCS:
            chroma_format_idc = reader.read_ue()
            if chroma_format_idc == 3:
                reader.read_bit()  # separate_colour_plane_flag
            reader.read_ue()  # bit_depth_luma_minus8
            reader.read_ue()  # bit_depth_chroma_minus8
            reader.read_bit()  # qpprime_y_zero_transform_bypass_flag
            if reader.read_bit():  # seq_scaling_matrix_present_flag
                count = 8 if chroma_format_idc != 3 else 12
                for i in range(count):
                    if reader.read_bit():
                        _skip_scaling_list(reader, 16 if i < 6 else 64)

        reader.read_ue()  # log2_max_frame_num_minus4
        poc_type = reader.read_ue()
        if poc_type == 0:
            reader.read_ue()  # log2_max_pic_order_cnt_lsb_minus4
        elif poc_type == 1:
            reader.read_bit()  # delta_pic_order_always_zero_flag
            reader.read_se()  # offset_for_non_ref_pic
            reader.read_se()  # offset_for_top_to_bottom_field
            for _ in range(reader.read_ue()):
                reader.read_se()

        reader.read_ue()  # max_num_ref_frames
        reader.read_bit()  # gaps_in_frame_num_value_allowed_flag
        pic_width_in_mbs = reader.read_ue() + 1
        pic_height_in_map_units = reader.read_ue() + 1
        frame_mbs_only = reader.read_bit()
        if not frame_mbs_only:
            reader.read_bit()  # mb_adaptive_frame_field_flag
        reader.read_bit()  # direct_8x8_inference_flag

        crop_left = crop_right = crop_top = crop_bottom = 0
        if reader.read_bit():  # frame_cropping_flag
            crop_left = reader.read_ue()
            crop_right = reader.read_ue()
            crop_top = reader.read_ue()
            crop_bottom = reader.read_ue()

        width = pic_width_in_mbs * 16
        height = pic_height_in_map_units * 16 * (2 - frame_mbs_only)

        # 裁剪单位由色度采样格式决定（H.264 规范 7.4.2.1.1）
        if chroma_format_idc == 0:
            crop_unit_x, crop_unit_y = 1, 2 - frame_mbs_only
        else:
            sub_width_c = 2 if chroma_format_idc in (1, 2) else 1
            sub_height_c = 2 if chroma_format_idc == 1 else 1
            crop_unit_x = sub_width_c
            crop_unit_y = sub_height_c * (2 - frame_mbs_only)

        width -= (crop_left + crop_right) * crop_unit_x
        height -= (crop_top + crop_bottom) * crop_unit_y
        if width <= 0 or height <= 0:
            return None
        return width, height
    except (ValueError, IndexError):
        return None


def extract_sps_dimensions(data: bytes) -> tuple[int, int] | None:
    """在 H.264 数据包中查找 SPS 并解析宽高。

    Args:
        data: 原始 H.264 数据包（可能含多个 NAL 单元）

    Returns:
        (width, height)，无 SPS 或解析失败返回 None
    """
    for nal_type, nal in parse_nal_units(data):
        if nal_type == NAL_SPS:
            return parse_sps_dimensions(_strip_start_code(nal))
    return None


def is_key_frame(data: bytes) -> bool:
    """判断 H.264 数据包是否包含关键帧（IDR 或 SPS）。"""
    for nal_type, _ in parse_nal_units(data):
        if nal_type in (NAL_IDR, NAL_SPS):
            return True
    return False


def has_config_data(data: bytes) -> bool:
    """判断数据包是否包含编解码器配置（SPS/PPS）。"""
    for nal_type, _ in parse_nal_units(data):
        if nal_type in (NAL_SPS, NAL_PPS):
            return True
    return False


# ─── 控制指令编码 ───


def encode_inject_keycode(action: int, keycode: int, repeat: int = 0, metastate: int = 0) -> bytes:
    """编码按键注入指令。"""
    return struct.pack(
        ">BBIII",
        CONTROL_TYPE_INJECT_KEYCODE,
        action,
        keycode,
        repeat,
        metastate,
    )


def encode_inject_text(text: str) -> bytes:
    """编码文本注入指令。"""
    text_bytes = text.encode("utf-8")
    return struct.pack(">BI", CONTROL_TYPE_INJECT_TEXT, len(text_bytes)) + text_bytes


def encode_inject_touch(
    action: int,
    pointer_id: int,
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    pressure: float = 1.0,
    action_button: int = 0,
    buttons: int = 0,
) -> bytes:
    """编码触控注入指令。

    scrcpy v3 touch 格式：
    type(1) + action(1) + pointerId(8) + position(x:4 + y:4 + w:2 + h:2) +
    pressure(2) + actionButton(4) + buttons(4)
    """
    # pressure 转为 uint16（0~0xFFFF）
    pressure_u16 = min(int(pressure * 0xFFFF), 0xFFFF)

    return struct.pack(
        ">BBqiiHHHII",
        CONTROL_TYPE_INJECT_TOUCH,
        action,
        pointer_id,
        x,
        y,
        screen_width,
        screen_height,
        pressure_u16,
        action_button,
        buttons,
    )


def _float_to_i16fp(value: float) -> int:
    """将 [-1.0, 1.0] 浮点滚动量转为 i16 定点数（scrcpy ≥1.25 协议）。"""
    clamped = max(-1.0, min(1.0, value))
    return max(-0x8000, min(0x7FFF, round(clamped * 0x7FFF)))


def encode_inject_scroll(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    h_scroll: float,
    v_scroll: float,
    buttons: int = 0,
) -> bytes:
    """编码滚动注入指令。

    scrcpy ≥1.25 格式（共 21 字节）：
    type(1) + position(x:4 + y:4 + w:2 + h:2) + hscroll(2) + vscroll(2) + buttons(4)
    其中 hscroll/vscroll 为 i16 定点数（-1.0~1.0 映射 -32768~32767）。
    """
    return struct.pack(
        ">BiiHHhhI",
        CONTROL_TYPE_INJECT_SCROLL,
        x,
        y,
        screen_width,
        screen_height,
        _float_to_i16fp(h_scroll),
        _float_to_i16fp(v_scroll),
        buttons,
    )


def encode_back_or_screen_on(action: int) -> bytes:
    """编码返回键/亮屏指令。"""
    return struct.pack(">BB", CONTROL_TYPE_BACK_OR_SCREEN_ON, action)


def encode_set_screen_power_mode(mode: int) -> bytes:
    """编码屏幕电源模式指令。mode: 0=OFF, 2=NORMAL。"""
    return struct.pack(">BB", CONTROL_TYPE_SET_SCREEN_POWER_MODE, mode)


def encode_expand_notification_panel() -> bytes:
    """编码展开通知栏指令。"""
    return struct.pack(">B", CONTROL_TYPE_EXPAND_NOTIFICATION_PANEL)


def encode_expand_settings_panel() -> bytes:
    """编码展开设置面板指令。"""
    return struct.pack(">B", CONTROL_TYPE_EXPAND_SETTINGS_PANEL)


def encode_collapse_panels() -> bytes:
    """编码折叠面板指令。"""
    return struct.pack(">B", CONTROL_TYPE_COLLAPSE_PANELS)


def encode_set_clipboard(text: str, paste: bool = False) -> bytes:
    """编码设置剪贴板指令。

    scrcpy v3 格式：type(1) + sequence(8) + paste(1) + length(4) + text
    """
    text_bytes = text.encode("utf-8")
    return struct.pack(
        ">BqBI",
        CONTROL_TYPE_SET_CLIPBOARD,
        0,  # sequence
        1 if paste else 0,
        len(text_bytes),
    ) + text_bytes


def encode_rotate_device() -> bytes:
    """编码旋转设备指令。"""
    return struct.pack(">B", CONTROL_TYPE_ROTATE_DEVICE)


# ─── 设备消息解析（scrcpy device → PC） ───

# 设备消息类型
DEVICE_MSG_TYPE_CLIPBOARD = 0
DEVICE_MSG_TYPE_ACK_CLIPBOARD = 1
DEVICE_MSG_TYPE_UHID_OUTPUT = 2


def parse_device_message_with_size(data: bytes) -> tuple[dict | None, int]:
    """解析一条 scrcpy 设备消息，并返回已消费字节数。"""
    if not data:
        return None, 0

    msg_type = data[0]

    if msg_type == DEVICE_MSG_TYPE_CLIPBOARD:
        if len(data) < 5:
            return None, 0
        text_len = struct.unpack(">I", data[1:5])[0]
        size = 5 + text_len
        if len(data) < size:
            return None, 0
        text = data[5:size].decode("utf-8", errors="replace")
        return {"type": "clipboard", "text": text}, size

    if msg_type == DEVICE_MSG_TYPE_ACK_CLIPBOARD:
        if len(data) < 9:
            return None, 0
        sequence = struct.unpack(">q", data[1:9])[0]
        return {"type": "ack_clipboard", "sequence": sequence}, 9

    return None, 1


def parse_device_message(data: bytes) -> dict | None:
    """解析 scrcpy 设备消息。

    设备消息格式：
    - TYPE_CLIPBOARD(0): type(1) + length(4) + text(length)
    - TYPE_ACK_CLIPBOARD(1): type(1) + sequence(8)

    Returns:
        解析后的消息字典，或 None（未知类型）
    """
    message, _ = parse_device_message_with_size(data)
    return message
