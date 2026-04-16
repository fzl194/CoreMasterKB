# 添加APN（ADD APN）（ADD APN）

## 命令功能

['适用NF：PGW-C', '该命令用于创建APN对象，并定义APN名称、地址类型、关联地址池和缺省策略。']

## 注意事项

['APN名称需与签约数据保持一致。', '若APN由PGW-U本地分配地址，需同时准备地址池和Sxb控制能力。', '变更生产APN前应确认不影响现网签约和DNS。']

## 操作用户权限

G_1，管理员级别命令组；G_2，操作员级别命令组

## 参数说明

[['表头：', '参数标识', '参数名称', '参数说明'], ['第1行：', 'APNNAME', 'APN名称', '必选参数。指定APN标识。'], ['第2行：', 'PDNTYPE', 'PDN地址类型', '必选参数。可选IPV4、IPV6、IPV4V6。'], ['第3行：', 'POOLNAME', '地址池名称', '可选参数。用于绑定本地地址池。'], ['第4行：', 'DNSPROFILE', 'DNS模板', '可选参数。指定下发到用户侧的DNS信息。'], ['第5行：', 'DESC', '描述', '可选参数。用于维护备注。']]

## 使用实例

['新增APN internet：', 'ADD APN:APNNAME="internet",PDNTYPE=IPV4,POOLNAME="pool_ipv4",DNSPROFILE="dns_public";', '新增双栈APN ims：', 'ADD APN:APNNAME="ims",PDNTYPE=IPV4V6,POOLNAME="pool_dual",DNSPROFILE="dns_ims";']
