# MyPhishing
钓鱼邮件检测网关


## DNS解析配置
为了让全局邮件先到你的 Python 网关，需要修改 MX 记录：

假设你域名是 hanyinfo.xyz：

记录类型	主机名	值	描述
MX	@	     mail.hanyinfo.xyz	     收件服务器，优先级 10
A	mail	公网 IP（你的服务器 IP）	mail.hanyinfo.xyz  指向公网 IP

说明：

外部邮件服务器发邮件给 @hanyinfo.xyz

根据 MX 记录 → 发到 mail.hanyinfo.xyz → 也就是你的 Python 网关

Python 网关分析邮件 → 转发给 Maddy


外部邮件发过来
        │
        ▼
[Python AI Mail Gateway]  <-- 判断是否钓鱼
        │
        │  (SMTP转发)
        ▼
[Maddy 邮件服务器]  <-- 本地收发、存储邮件
        │
        ▼
用户客户端 (IMAP/SMTP)

Python 网关：监听 SMTP 端口（25），接收所有外部邮件 → 分析邮件 → 判断是否钓鱼

钓鱼邮件：拦截，不投递

正常邮件：通过 SMTP 转发到 Maddy 容器

Maddy：只接收来自 Python 网关的邮件 → 存储在 SQLite → 用户用 IMAP 读取

maddy创建用户邮箱命令：docker exec -it maddy maddy creds create user1@hyinfo.xyz

