# UI Design System（V1 冻结）— 双端视觉语言统一

> 原则：白色 + 深灰文字 + 单一品牌色。极简、克制、可读。不像素级复制，但 design token 必须一致。

---

## 1. Color Tokens（双端共用：手机 Flutter + 电脑 PySide6）
| Token | 值 | 用途 |
|-------|-----|------|
| bg | `#FFFFFF` | 背景 |
| surface | `#FAFAFA` | 次级表面（列表底色） |
| text-primary | `#111111` | 主文字 |
| text-secondary | `#777777` | 次文字 |
| border | `#EAEAEA` | 细边框 |
| brand | 单一品牌色（建议 `#2D7FF9` 蓝 或 `#111111` 黑） | 主操作 |
| danger | `#E5484D` | 删除/危险 |
| bubble-in | `#F2F2F2` | 对方气泡 |
| bubble-out | `brand` 浅化或 `#E8F0FE` | 自己气泡 |

**禁止**：渐变、玻璃拟态、复杂阴影、高饱和装饰、大面积彩色、过度圆角。

## 2. Typography（层级统一）
- H1 / 标题：17-20px，weight 600
- Body：14-15px，weight 400
- Caption：12px，text-secondary
- 字体：系统无衬线（iOS SF / Android Roboto / Windows Segoe UI），不引入花哨字体。

## 3. Spacing（统一间距体系）
4 / 8 / 12 / 16 / 24 px 阶梯。列表项上下 padding 12，左右 16。

## 4. Components（双端同构）
- **Button**：主按钮 brand 填充、次按钮描边、危险按钮 danger 描边。圆角 8px，不高圆。
- **Input**：白底、1px border、focus brand 边框，圆角 8px。
- **Avatar**：圆形，默认灰底首字母，可加载 avatar URL。
- **Message Bubble**：对方左、自己右；in 灰底、out brand 浅；圆角 12px；无复杂装饰。
- **List Item**：左 avatar + 中标题/副标题 + 右时间/未读角标。
- **Icon**：线性细图标，统一 stroke 1.5。

## 5. 平台布局差异（允许）
- **Flutter**：Bottom Navigation（Chats / Friends / Me）。
- **PySide6**：左侧 Sidebar（Chats / Friends / Settings）+ 中间聊天窗 + 底部输入框。
- 共同的：颜色、字体层级、按钮、输入框、头像、气泡、间距必须一致。

## 6. 暗色模式
V1 不做暗色（蓝图未要求，不提前扩展）。
