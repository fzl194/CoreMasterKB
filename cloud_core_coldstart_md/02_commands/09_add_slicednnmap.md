# 添加切片到DNN映射（ADD SLICEDNNMAP）（ADD SLICEDNNMAP）

## 命令功能

['适用NF：SMF', '该命令用于建立S-NSSAI与DNN之间的映射关系，以便按切片选择业务接入和UPF转发路径。']

## 注意事项

['切片到DNN映射应与签约、接入控制和UPF选择策略一致。', '同一切片下的多个DNN应有明确的业务区分。']

## 操作用户权限

G_1，管理员级别命令组；G_2，操作员级别命令组

## 参数说明

[['表头：', '参数标识', '参数名称', '参数说明'], ['第1行：', 'SNSSAI', '切片标识', '必选参数。格式通常包含SST和可选SD。'], ['第2行：', 'DNNNAME', 'DNN名称', '必选参数。指定映射到的DNN对象。'], ['第3行：', 'PRIORITY', '优先级', '可选参数。用于多映射场景下的选择顺序。'], ['第4行：', 'UPFSELGROUP', 'UPF选择组', '可选参数。用于限定该映射下的UPF选择范围。']]

## 使用实例

['为切片010203映射工业DNN：', 'ADD SLICEDNNMAP:SNSSAI="1-010203",DNNNAME="industrial",PRIORITY=10,UPFSELGROUP="upf_edge_ind";']
