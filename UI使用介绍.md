# Ebeam Data Visualizer UI 使用介绍

本文档面向日常使用者，说明如何通过 UI 完成 Ebeam 数据可视化。

## 1. 启动程序

如果使用脚本版：

```powershell
cd "D:\python demo\EbeamDataVisualizer"
python ui_app.py
```

如果使用打包后的程序，打开：

```text
dist\EbeamDataVisualizer\EbeamDataVisualizer.exe
```

注意：PyInstaller 打包后需要保留整个 `dist\EbeamDataVisualizer` 文件夹，不要只复制单独的 `.exe`。

## 2. UI 总体布局

界面分为左右两部分：

| 区域 | 作用 |
|---|---|
| 左侧控制区 | 选择数据文件、图表类型、字段、筛选条件、画图参数 |
| 右侧图表区 | 显示生成的图 |

左侧控制区会根据你选择的 `Chart type` 自动变化，只显示当前图表需要填写的参数。

## 3. 基本使用流程

1. 点击 `Browse` 选择数据文件。
2. 点击 `Load Columns` 读取字段。
3. 在 `Chart type` 中选择要画的图。
4. 设置当前图表显示出来的参数。
5. 点击 `Plot` 生成图。
6. 如需保存图片，点击 `Save PNG`。

## 4. 数据文件要求

推荐字段：

```text
WaferPosX
WaferPosY
ImageID
CD
BendingAngle
LayerType
LayerNO
Moduleindex
```

说明：

| 字段 | 用途 |
|---|---|
| `WaferPosX`, `WaferPosY` | 计算 radius 和 wafer heatmap |
| `ImageID` | 同一张 Ebeam 图的 ID |
| `CD` | 默认量测值 |
| `BendingAngle` | 可作为其它量测值绘图 |
| `LayerType`, `LayerNO`, `Moduleindex` | 区分不同 line/layer |

旧数据中如果字段叫 `ImageIDX`，程序也可以兼容读取。

## 5. 常用参数说明

### Value column

要画的数值列。

通常选择：

```text
CD
```

如果要画其它量测值，例如弯曲度，可以选择：

```text
BendingAngle
```

### Wafer center for Radius

用于计算 radius：

```text
Radius = sqrt((WaferPosX - X0)^2 + (WaferPosY - Y0)^2)
```

如果 wafer 坐标范围是 `-147 ~ +147` mm，通常：

```text
X0 = 0
Y0 = 0
```

### Radius bin

半径分段大小。

300mm wafer、坐标单位为 mm 时，建议：

```text
1, 2, 5, 10
```

如果 `Radius bin` 太大，例如 500，可能会导致整片 wafer 都落在一个 bin 里，图会失去趋势。

### Wafer / heatmap

热力图相关参数：

| 参数 | 说明 |
|---|---|
| `Diameter` | wafer 直径，300mm wafer 填 `300` |
| `Bin` | heatmap 网格大小，常用 `2`, `5`, `10` |
| `Color min` | 色阶最小值 |
| `Color max` | 色阶最大值 |
| `Map` | 颜色方案 |

如果要比较不同 wafer，请固定相同的 `Color min` 和 `Color max`。

## 6. 图表类型说明

### CD by wafer radius

用途：查看 CD 或其它数值列是否随 wafer 半径变化。

常用设置：

```text
Value column = CD
Radius bin = 2 或 5
X0 = 0
Y0 = 0
```

如果觉得图上元素太多，可以勾选：

```text
Radius chart line only
```

这样只显示均值线。

### Layer CD distribution

用途：查看不同 layer/line 的数值分布。

适合回答：

- 某个 layer 的 CD 是否偏移
- 不同 LayerNO 的分布是否有差异
- 某个量测值是否接近正态分布

常用设置：

```text
Value column = CD
Series display mode = Overlay selected series
```

### Line CD loading

用途：比较两条 line 的差异，并看差异是否随 radius 变化。

程序逻辑：

1. 在同一个 `ImageID` 内，对 Line A 的多个 CD 求均值。
2. 在同一个 `ImageID` 内，对 Line B 的多个 CD 求均值。
3. 按 `ImageID` 配对。
4. 计算 A-B、A+B 或 A/B。
5. 按 radius 画 loading。

常用设置：

```text
Line A: LayerType=M0, LayerNO=1
Line B: LayerType=M0, LayerNO=2
Operation = subtract
Radius bin = 2 或 5
```

### Wafer value heatmap

用途：在 wafer map 上查看某个数值列的空间分布。

适合回答：

- CD 是否有中心到边缘差异
- 某个区域是否异常
- BendingAngle 是否有空间 pattern

常用设置：

```text
Value column = CD
Diameter = 300
Bin = 5
Color min = 12
Color max = 15
```

如果画 `BendingAngle`，把 `Value column` 改成 `BendingAngle`。

### Wafer loading heatmap

用途：在 wafer map 上查看 Line A/B loading 的空间分布。

适合回答：

- 两条 line 的差异是否集中在某个 wafer 区域
- loading 是否有 edge、center 或 quadrant pattern

常用设置：

```text
Line A: LayerType=M0, LayerNO=1
Line B: LayerType=M0, LayerNO=2
Operation = subtract
Diameter = 300
Bin = 5
Map = coolwarm
Color min = -0.5
Color max = 0.5
```

### Custom X-Y scatter

用途：自由选择 X/Y 轴画散点图。

常用设置：

```text
X axis = Radius
Y axis = CD
Data mode = Sample
Scatter mean by ImageID = 勾选
```

建议默认勾选 `Scatter mean by ImageID`，这样每个 ImageID 只画一个平均点，图会更清楚。

## 7. 筛选功能

### Visible layer values

用于普通图表筛选：

- CD by wafer radius
- Layer distribution
- Wafer value heatmap
- Custom X-Y scatter

可以手动输入：

```text
LayerType = M0,M1
LayerNO = 1,2
Moduleindex = 0
```

也可以点击：

```text
Choose visible values...
```

### Line A / Line B filters

用于：

- Line CD loading
- Wafer loading heatmap

示例：

```text
Line A LayerType = M0
Line A LayerNO = 1

Line B LayerType = M0
Line B LayerNO = 2
```

如果筛选混乱，可以点击：

```text
Clear visible filters
Clear Line A/B filters
```

## 8. Series display mode

| 模式 | 说明 |
|---|---|
| `Combine selected data` | 把筛选后的数据合在一起画 |
| `Overlay selected series` | 多个 layer/line 叠加在同一张图 |
| `Separate panels` | 多个 layer/line 分开画成子图 |

如果要比较不同 line，通常选择：

```text
Overlay selected series
```

如果线太多、重叠严重，可以选择：

```text
Separate panels
```

## 9. 保存图片

画图完成后点击：

```text
Save PNG
```

选择保存路径即可。

## 10. 常见问题

### No valid data found

说明当前筛选条件没有匹配到数据。

处理方式：

1. 点击 `Clear visible filters`。
2. 点击 `Clear Line A/B filters`。
3. 点击 `Show available values` 查看真实存在的 LayerType、LayerNO、Moduleindex。
4. 确认 Line A 和 Line B 在同一个 `ImageID` 下同时存在。

### CD by radius 图只有一个点

通常是 `Radius bin` 太大。

300mm wafer、mm 坐标建议：

```text
Radius bin = 2 或 5
```

### Heatmap 颜色不好比较

不同 wafer 比较时，必须固定：

```text
Color min
Color max
```

否则每张图会自动缩放色阶，看起来颜色相似但数值范围可能不同。

### 图上点太多

Custom scatter 建议：

```text
Data mode = Sample
Scatter mean by ImageID = 勾选
```

## 11. 推荐起步配置

如果你的数据是 300mm wafer，坐标范围约 `-147 ~ +147` mm，可以先用：

```text
Value column = CD
X0 = 0
Y0 = 0
Radius bin = 2
Wafer diameter = 300
Heatmap bin = 5
```

如果 CD 大约在 `12 ~ 15`，heatmap 可以先设置：

```text
Color min = 12
Color max = 15
```

