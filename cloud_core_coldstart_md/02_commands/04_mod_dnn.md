# 修改DNN（MOD DNN）（MOD DNN）

## 命令功能

['适用NF：SMF', '该命令用于修改已存在DNN的地址类型、地址池、DNS模板或UPF选择组等属性。']

## 注意事项

['修改DNN可能影响新建会话，部分参数修改后不追溯已建立会话。', '涉及地址池、UPF选择或本地分流策略变更时，建议在低峰时段实施。', '若现网已有大量用户，修改前应评估回退方案。']

## 操作用户权限

G_1，管理员级别命令组；G_2，操作员级别命令组

## 参数说明

[['表头：', '参数标识', '参数名称', '参数说明'], ['第1行：', 'DNNNAME', 'DNN名称', '必选参数。指定待修改的DNN。'], ['第2行：', 'ADDRTYPE', '会话地址类型', '可选参数。修改DNN支持的地址类型。'], ['第3行：', 'POOLNAME', '默认地址池', '可选参数。修改DNN绑定的默认地址池。'], ['第4行：', 'DNSPROFILE', 'DNS模板', '可选参数。修改终端下发的DNS相关配置。'], ['第5行：', 'UPFSELGROUP', 'UPF选择组', '可选参数。变更该DNN的UPF选择范围。']]

## 使用实例

['将DNN internet的地址池切换为pool_ipv4_b：', 'MOD DNN:DNNNAME="internet",POOLNAME="pool_ipv4_b";', '将DNN ims升级为双栈：', 'MOD DNN:DNNNAME="ims",ADDRTYPE=IPV4V6,POOLNAME="pool_dual";']
