---
name: code-review
description: 自动化代码审查流程。运行代码质量检查工具（Flake8、Black、isort、Mypy），同时进行深度架构审查（SOLID原则、安全风险、代码质量），并提供修复建议。
---

# 代码审查技能

此技能提供自动化的代码审查流程，结合 Ruff 工具检查与资深工程师视角的深度架构审查，确保代码符合项目规范和质量标准。

## 何时使用

**触发条件：**
- 用户完成代码修改后
- 用户要求进行代码审查
- 用户提交代码前（git commit 之前）
- 用户明确提到 "review"、"检查"、"质量"

**自动触发：**
- 每次使用 Edit/Write 工具修改 Python 代码后
- 创建新的 Python 模块后

---

## 审查流程

### 第一步：预检上下文

- 使用 `git status -sb`、`git diff --stat` 和 `git diff` 确定变更范围
- 如有需要，使用搜索工具查找相关模块、调用方和接口契约
- 识别入口点、所有权边界和关键路径（认证、设备控制、视频流、WebSocket）

**边界情况处理：**
- **无变更**：若 `git diff` 为空，告知用户并询问是否审查暂存区或指定提交范围
- **大型 diff（>500 行）**：先按文件汇总，再按模块/功能区域分批审查
- **混合关注点**：按逻辑功能分组，而非按文件顺序

### 第二步：运行 Ruff 代码质量工具

自动执行 Ruff 检查与格式化：

1. **Ruff 代码检查**
   ```bash
   uv run ruff check backend/
   ```

2. **Ruff 自动修复（安全修复）**
   ```bash
   uv run ruff check backend/ --fix
   ```

3. **Ruff 代码格式化**
   ```bash
   uv run ruff format backend/
   ```

4. **查看未修复的问题（如有）**
   ```bash
   uv run ruff check backend/ --statistics
   ```

### 第三步：SOLID 原则与架构审查

加载 `references/solid-principles.md` 进行专项检查：

- **SRP（单一职责）**：模块是否承担了不相关的多个职责（如设备发现与视频流转发混在一起）
- **OCP（开闭原则）**：添加新设备类型（iOS/Android）是否需要修改核心逻辑而非扩展抽象类
- **LSP（里氏替换）**：子类（`IOSDriver`、`AndroidDriver`）是否破坏了 `AbstractDeviceDriver` 的行为预期
- **ISP（接口隔离）**：驱动接口是否过宽，实现方存在大量未使用的方法
- **DIP（依赖倒置）**：高层设备管理是否直接依赖具体 ADB 命令或 Tidevice API

提出重构建议时，说明*为何*能改善内聚性/耦合度，并给出最小化、安全的拆分方案。若重构非轻量级，提出渐进式计划而非大规模重写。

### 第四步：冗余代码识别与迭代计划

加载 `references/cleanup-plan.md` 作为模板：

- 识别未使用、冗余或已关闭特性开关的代码
- 区分**立即可安全删除**与**需要计划后延迟删除**
- 提供包含具体步骤和检查点（测试/指标）的后续计划

### 第五步：安全与可靠性扫描

加载 `references/security-risks.md` 进行全面检查：

- 命令注入：通过 `subprocess` 调用 ADB、scrcpy、go-ios 时的参数拼接风险
- WebSocket 安全：未验证的帧大小导致内存溢出、跨域配置不当
- 资源泄露：子进程未正确回收、端口转发未释放、文件描述符耗尽
- 认证/授权：Web 端访问是否需要身份验证（当前设计无认证，需评估暴露风险）
- 并发安全：多设备同时操作时的竞态条件、`asyncio` 任务取消处理
- 日志敏感信息：ADB 序列号、设备 IP 是否明文记录

同时指出**可利用性**和**影响范围**。

### 第六步：代码质量扫描

加载 `references/code-quality.md` 进行检查：

- **错误处理**：吞掉的异常（`except: pass`）、过宽的 `except Exception`、异步任务未捕获异常
- **性能**：视频流处理中的内存拷贝、MJPEG 解析效率、WebSocket 背压控制
- **边界条件**：设备断连时的状态清理、空设备列表的 UI 处理、端口号耗尽
- **异步代码**：`async` 函数内调用阻塞 I/O（如 `subprocess.run` 而非 `asyncio.create_subprocess_exec`）

标记可能导致静默失败或生产事故的问题。

### 第七步：分析 Ruff 检查结果

根据 Ruff 输出分析问题类型：

#### 常见问题及修复

| 规则代码 | 问题描述               | 自动修复 | 手动处理方式                 |
| :------- | :--------------------- | :------: | :--------------------------- |
| F401     | 导入但未使用           |    ✅     | `ruff check --fix` 自动移除  |
| F841     | 变量定义但未使用       |    ✅     | 同上                         |
| E501     | 行过长（超过配置长度） |    ✅     | `ruff format` 自动换行       |
| I001     | 导入未排序             |    ✅     | `ruff check --fix` 自动排序  |
| UP006    | 使用弃用的类型写法     |    ✅     | 自动替换为 `list`、`dict` 等 |
| B006     | 可变默认参数           |    ❌     | 改为 `None` 并在函数内初始化 |
| B007     | 循环内未使用的变量     |    ❌     | 改为 `_` 或删除              |
| C401     | 不必要的生成器表达式   |    ✅     | 自动简化                     |
| SIM102   | 嵌套 `if` 可合并       |    ✅     | 自动合并                     |
| RUF100   | 未使用的 `# noqa` 注释 |    ✅     | 自动移除                     |

**不可自动修复的规则**需要人工审查并修改代码。

### 第八步：生成审查报告

```
## 代码审查报告

**审查文件**：X 个文件，Y 行变更
**总体评估**：[批准 / 请求修改 / 仅评论]

---

## 发现问题

### P0 - 严重（阻塞合并）
（无 或 列表）

### P1 - 高优先级
1. **[文件:行号]** 简要标题
   - 问题描述
   - 修复建议

### P2 - 中优先级
2. （跨章节连续编号）
   - ...

### P3 - 低优先级
...

---

### ✅ 工具检查结果
- Ruff 检查：X 个问题（Y 个已自动修复，Z 个待处理）
- Ruff 格式化：已完成

### 📊 统计信息
- 检查文件数: X
- 发现问题总数: Y
- 自动修复数: Z
- 代码质量: 优秀/良好/需改进

## 冗余代码/迭代计划
（如适用）

## 补充建议
（可选改进，不阻塞合并）
```

**行内注释**：针对具体文件的发现使用以下格式：
```
::code-comment{file="path/to/file.py" line="42" severity="P1"}
问题描述及修复建议。
::
```

**无问题时**：若未发现问题，明确说明：
- 检查了哪些内容
- 哪些方面未覆盖（如"未验证设备端行为"）
- 残余风险或建议的后续测试

### 第九步：确认下一步操作

展示发现后，询问用户如何继续：

```
---

## 下一步

发现 X 个问题（P0: _, P1: _, P2: _, P3: _）。

**您希望如何处理？**

1. **全部修复** - 实施所有建议的修复
2. **仅修复 P0/P1** - 处理严重和高优先级问题
3. **修复指定项** - 告诉我修复哪些问题
4. **无需修改** - 审查完成，不需要实施

请选择一个选项或提供具体指示。
```

**重要**：在用户明确确认之前，不要实施任何修改。这是审查优先的工作流。

---

## 自动修复常见问题

对于 Ruff 能够自动修复的规则，直接执行 `ruff check --fix` 并告知用户。对于需要手动干预的问题，提供具体的修复代码片段。

### 修复示例

#### 1. 可变默认参数（B006）
```python
# 修复前
def start_mirroring(device_id: str, options: dict = {}):

# 修复后
def start_mirroring(device_id: str, options: dict | None = None):
    if options is None:
        options = {}
```

#### 2. 过宽异常捕获
```python
# 修复前
try:
    adb.device(serial)
except:
    return None

# 修复后
try:
    adb.device(serial)
except adbutils.AdbError as e:
    logger.warning(f"Device {serial} not found: {e}")
    return None
```

#### 3. 异步阻塞 I/O
```python
# 修复前
async def list_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True)

# 修复后
async def list_devices():
    proc = await asyncio.create_subprocess_exec(
        "adb", "devices",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
```

---

## 项目特定配置

### Ruff 配置（pyproject.toml）
```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # 行长度由 formatter 处理

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 代码规范摘要
- 最大行长度：100 字符
- Python 版本：3.13
- 格式化：Ruff format
- 导入排序：Ruff（isort 规则）
- 代码检查：Ruff（集成 Flake8、pyflakes、pyupgrade、flake8-bugbear 等）

---

## 与 Git 集成

### Pre-commit 钩子（可选）
若项目配置了 pre-commit，可在提交前自动运行 Ruff：

```bash
# 首次安装钩子
uv run pre-commit install

# 手动运行所有检查
uv run pre-commit run --all-files
```

### Git 工作流程

1. 修改代码
2. 运行审查命令：
   ```bash
   uv run ruff check backend/ --fix
   uv run ruff format backend/
   ```
3. 查看审查结果并手动修复剩余问题
4. 暂存变更：`git add .`
5. 提交代码：`git commit -m "feat(scope): description"`
6. 推送分支：`git push origin feature/xxx`

### Commit Message 规范
遵循 Conventional Commits 格式，审查通过后的提交信息应包含审查引用（如 PR 编号）。

---

## 注意事项

⚠️ **重要提醒：**
- Ruff 是唯一的代码质量工具，**不要**再使用 Flake8、Black、isort 或 Mypy（除非项目明确需要类型检查）
- Ruff 的自动修复安全可靠，建议每次审查前先运行 `--fix`
- 审查发现的安全问题（P0）必须阻塞合并，不得绕过
- 对于异步代码，特别留意事件循环阻塞问题

📝 **文档同步：**
- 若修改了公开接口或配置项，须同步更新 `CLAUDE.md` 或相关文档

🔒 **禁止忽略：**
- 命令注入风险（`subprocess` 参数拼接）
- WebSocket 未限制帧大小
- 设备断连后的资源泄露
- 并发操作竞态条件

---

## 快速命令

```bash
# 完整审查流程（检查 + 修复 + 格式化）
uv run ruff check backend/ --fix && uv run ruff format backend/

# 仅检查不修改
uv run ruff check backend/

# 查看统计信息
uv run ruff check backend/ --statistics

# 忽略特定规则（临时使用）
uv run ruff check backend/ --ignore SIM102
```

---

## 参考资料

| 文件                             | 用途                               |
| -------------------------------- | ---------------------------------- |
| `references/solid-principles.md` | SOLID 代码异味提示与重构启发式方法 |
| `references/security-risks.md`   | Web/应用安全与运行时风险清单       |
| `references/code-quality.md`     | 错误处理、性能、边界条件           |
| `references/cleanup-plan.md`     | 删除候选项与后续计划模板           |

---

## 示例对话

**用户**："我刚修改了 android.py"

**Claude**：
好的，让我对 `backend/app/drivers/android.py` 进行代码审查...

[运行 Ruff 检查 + 深度审查]

✅ 审查完成！Ruff 自动修复了 2 个问题（未使用导入、导入排序）。无其他架构或安全问题。代码符合规范。

**用户**："帮我审查整个后端"

**Claude**：
正在对 `backend/` 进行完整代码审查...

[运行 Ruff 检查 + 架构审查 + 安全扫描]

📊 审查报告：
- 检查文件：15 个
- Ruff 问题：0（已全部自动修复）
- 架构问题：0
- 安全风险：0

✅ 代码质量：优秀，所有检查通过！