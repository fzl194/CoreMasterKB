# 添加DNS模板（ADD DNSPROFILE）（ADD DNSPROFILE）

## 命令功能

['适用NF：SMF、PGW-C', '该命令用于创建DNS模板，供DNN/APN对象引用，用于向终端下发DNS服务器信息。']

## 注意事项

['建议按业务场景区分公共互联网、IMS、企业专网等不同DNS模板。', '双栈业务建议同时规划IPv4 DNS和IPv6 DNS。']

## 操作用户权限

G_1，管理员级别命令组；G_2，操作员级别命令组

## 参数说明

[['表头：', '参数标识', '参数名称', '参数说明'], ['第1行：', 'PROFILENAME', '模板名称', '必选参数。唯一标识DNS模板。'], ['第2行：', 'PRIMARYDNSV4', '主IPv4 DNS', '可选参数。配置主用IPv4 DNS地址。'], ['第3行：', 'SECONDDNSV4', '备IPv4 DNS', '可选参数。配置备用IPv4 DNS地址。'], ['第4行：', 'PRIMARYDNSV6', '主IPv6 DNS', '可选参数。配置主用IPv6 DNS地址。'], ['第5行：', 'SECONDDNSV6', '备IPv6 DNS', '可选参数。配置备用IPv6 DNS地址。']]

## 使用实例

['新增公网DNS模板：', 'ADD DNSPROFILE:PROFILENAME="dns_public",PRIMARYDNSV4="8.8.8.8",SECONDDNSV4="8.8.4.4";']
