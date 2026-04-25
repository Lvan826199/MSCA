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
    # 查找 start code（0x00000001 或 0x000001）
    i = 0
    starts = []
    while i < len(data) - 3:
        if data[i : i + 4] == b"\x00\x00\x00\x01":
            starts.append(i + 4)
            i += 4
        elif data[i : i + 3] == b"\x00\x00\x01":
            starts.append(i + 3)
            i += 3
        else:
            i += 1

    if not starts:
        # 没有 start code，整个数据作为一个 NAL
        if len(data) > 0:
            nal_type = data[0] & NAL_TYPE_MASK
            units.append((nal_type, data))
        return units

    for idx, start in enumerate(starts):
        end = starts[idx + 1] - 4 if idx + 1 < len(starts) else len(data)
        # 回退 start code 长度
        if idx + 1 < len(starts):
            # 检查下一个 start code 是 3 字节还是 4 字节
            sc_pos = starts[idx + 1]
            if sc_pos >= 4 and data[sc_pos - 4 : sc_pos - 4 + 4] == b"\x00\x00\x00\x01":
                end = sc_pos - 4
            else:
                end = sc_pos - 3

        nal_data = data[start:end]
        if len(nal_data) > 0:
            nal_type = nal_data[0] & NAL_TYPE_MASK
            units.append((nal_type, data[start - 4 : end] if start >= 4 else data[start - 3 : end]))

    return units


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


def encode_inject_scroll(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
    h_scroll: int,
    v_scroll: int,
    buttons: int = 0,
) -> bytes:
    """编码滚动注入指令。"""
    return struct.pack(
        ">BiiHHiiI",
        CONTROL_TYPE_INJECT_SCROLL,
        x,
        y,
        screen_width,
        screen_height,
        h_scroll,
        v_scroll,
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


def encode_expand_notification_panel() -> bytes:
    """展开通知栏。"""
    return struct.pack(">B", CONTROL_TYPE_EXPAND_NOTIFICATION_PANEL)


def encode_expand_settings_panel() -> bytes:
    """展开设置面板（快捷开关）。"""
    return struct.pack(">B", CONTROL_TYPE_EXPAND_SETTINGS_PANEL)


def encode_collapse_panels() -> bytes:
    """收起通知栏/设置面板。"""
    return struct.pack(">B", CONTROL_TYPE_COLLAPSE_PANELS)


def encode_set_clipboard(text: str, paste: bool = False) -> bytes:
    """设置设备剪贴板内容。

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
    """旋转设备屏幕。"""
    return struct.pack(">B", CONTROL_TYPE_ROTATE_DEVICE)
