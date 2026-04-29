import { ElButton } from "element-plus/es/components/button/index"
import { ElCard } from "element-plus/es/components/card/index"
import { ElCheckbox, ElCheckboxGroup } from "element-plus/es/components/checkbox/index"
import { ElConfigProvider } from "element-plus/es/components/config-provider/index"
import { ElAside, ElContainer, ElMain } from "element-plus/es/components/container/index"
import { ElDialog } from "element-plus/es/components/dialog/index"
import { ElDivider } from "element-plus/es/components/divider/index"
import { ElEmpty } from "element-plus/es/components/empty/index"
import { ElForm, ElFormItem } from "element-plus/es/components/form/index"
import { ElIcon } from "element-plus/es/components/icon/index"
import { ElInput } from "element-plus/es/components/input/index"
import { ElMenu, ElMenuItem } from "element-plus/es/components/menu/index"
import { ElOption, ElSelect } from "element-plus/es/components/select/index"
import { ElSwitch } from "element-plus/es/components/switch/index"
import { ElTabPane, ElTabs } from "element-plus/es/components/tabs/index"
import { ElTag } from "element-plus/es/components/tag/index"
import { ElTooltip } from "element-plus/es/components/tooltip/index"

import "element-plus/theme-chalk/base.css"
import "element-plus/es/components/aside/style/css"
import "element-plus/es/components/button/style/css"
import "element-plus/es/components/card/style/css"
import "element-plus/es/components/checkbox/style/css"
import "element-plus/es/components/checkbox-group/style/css"
import "element-plus/es/components/config-provider/style/css"
import "element-plus/es/components/container/style/css"
import "element-plus/es/components/dialog/style/css"
import "element-plus/es/components/divider/style/css"
import "element-plus/es/components/empty/style/css"
import "element-plus/es/components/form/style/css"
import "element-plus/es/components/form-item/style/css"
import "element-plus/es/components/icon/style/css"
import "element-plus/es/components/input/style/css"
import "element-plus/es/components/main/style/css"
import "element-plus/es/components/menu/style/css"
import "element-plus/es/components/menu-item/style/css"
import "element-plus/es/components/message/style/css"
import "element-plus/es/components/option/style/css"
import "element-plus/es/components/select/style/css"
import "element-plus/es/components/switch/style/css"
import "element-plus/es/components/tab-pane/style/css"
import "element-plus/es/components/tabs/style/css"
import "element-plus/es/components/tag/style/css"
import "element-plus/es/components/tooltip/style/css"

const components = [
  ElAside,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElConfigProvider,
  ElContainer,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTabPane,
  ElTabs,
  ElTag,
  ElTooltip,
]

export function installElementPlus(app) {
  for (const component of components) {
    app.component(component.name, component)
  }
}
