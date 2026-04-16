# 添加DNN（ADD DNN）（ADD DNN）

## 命令功能

['适用NF：SMF', '该命令用于创建DNN对象，并定义DNN名称、会话地址类型、默认地址池和关联策略。']

## 注意事项

['该命令执行后立即生效。', '新增DNN前应确认签约、DNS、地址池和UPF选择策略已准备完成。', 'DNN名称应与终端侧使用和签约数据保持一致。', '若启用双栈，应保证IPv4和IPv6地址池均可用。']

## 操作用户权限

G_1，管理员级别命令组；G_2，操作员级别命令组

## 参数说明

[['表头：', '参数标识', '参数名称', '参数说明'], ['第1行：', 'DNNNAME', 'DNN名称', '必选参数。用于唯一标识数据网络名称。'], ['第2行：', 'ADDRTYPE', '会话地址类型', '必选参数。可选IPV4、IPV6、IPV4V6。'], ['第3行：', 'POOLNAME', '默认地址池', '条件必选参数。使用本地地址分配时建议配置默认地址池。'], ['第4行：', 'DNSPROFILE', 'DNS模板', '可选参数。用于向终端下发DNS相关信息。'], ['第5行：', 'UPFSELGROUP', 'UPF选择组', '可选参数。用于约束该DNN对应的UPF选择范围。'], ['第6行：', 'DESC', '描述', '可选参数。用于维护备注。']]

## 使用实例

['新增IPv4 DNN internet：', 'ADD DNN:DNNNAME="internet",ADDRTYPE=IPV4,POOLNAME="pool_ipv4",DNSPROFILE="dns_public",UPFSELGROUP="upf_default";', '新增双栈DNN ims：', 'ADD DNN:DNNNAME="ims",ADDRTYPE=IPV4V6,POOLNAME="pool_dual",DNSPROFILE="dns_ims",UPFSELGROUP="upf_edge";']
