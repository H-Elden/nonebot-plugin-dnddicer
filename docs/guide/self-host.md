# 自建查询服务（可选）

规则查询默认使用公开的在线查询服务，只需在插件里打开开关，不需要你做任何部署。

如果你希望把这一环掌握在自己手里——不受第三方服务波动、维护或长期可用性的影响，也不想给上游站添压力——可以在自己的服务器上部署一份查询服务，让骰娘改走本机访问。查询速度也会更快（本机几十毫秒，公网一两百毫秒起步）。

本页只讲服务端的部署；插件侧的开关与调优（含图片模式与字体要求）见[快速开始 - 规则查询（可选）](./quickstart.md#规则查询-可选)，玩家侧用法与可查书目见[规则查询](./query.md)。

本页给出两种方案，按服务器的内存挑一种：

| 服务器内存 | 建议 |
| --- | --- |
| 4GB 及以上 | **方案一：完整自建**（推荐，步骤见下） |
| 2GB | 方案二：补丁版 + swap（可行，但见方案二的前置提醒） |
| 可用内存已不足 1GB | 不建议自建，继续用默认的在线服务 |

先说清楚「部署的是什么」：只需要跑一个查询服务进程（它把一份约 60MB 的索引读进内存，对外提供检索接口），**不需要**部署那套给人阅读的整站页面。整套东西约占 65MB 磁盘、常驻内存约 0.25~0.4GB。

## 方案一：4GB 及以上，完整自建

以下以 Ubuntu / Debian 为例；其他发行版把包管理命令换成对应的即可。

**第 0 步：确认前提**

```bash
free -h && nproc && df -h
```

内存一项看 `available`：4GB 机器通常有 3GB 以上，足够。磁盘留出 200MB 即可。

**第 1 步：安装 Node.js（18 或更高）**

```bash
node -v || sudo apt-get install -y nodejs npm
```

如果发行版自带的版本低于 18（`node -v` 会告诉你），改用 NodeSource 源或官网二进制包安装。

**第 2 步：取查询服务源码（4 个文件）**

```bash
mkdir -p ~/5echm-search && cd ~/5echm-search
for f in server.js config.js data-updater.js package.json; do
  curl -fsSL "https://cdn.jsdelivr.net/gh/DND5eChm/5echmweb_search@main/$f" -o "$f"
done
```

**第 3 步：安装依赖**

```bash
npm config set registry https://registry.npmmirror.com
npm install --omit=dev --no-audit --no-fund
```

**第 4 步：准备索引文件**

可以跳过这步——首次启动会自动下载。想先手动放好（国内从官方镜像拉更稳）就用：

```bash
curl -fsSL -o data.js "https://5echmsearch.kagangtuya.top/data.js"
```

这个索引文件是查询服务的数据本体，约 60MB，由上游项目随内容更新自动构建。

**第 5 步：前台跑一次，确认能用**

```bash
PORT=13000 node server.js
```

看到「已加载 8193 条数据」与「服务器运行在 `http://localhost:13000`」即可。另开一个终端验证：

```bash
curl -s "http://127.0.0.1:13000/api/filters" | head -c 200
curl -s "http://127.0.0.1:13000/api/search?keyword=%E7%81%AB%E7%90%83%E6%9C%AF&pageSize=3" | head -c 200
```

两条都能返回 JSON 就成功了，`Ctrl+C` 停掉，交给下面的常驻配置。

**第 6 步：配置为系统服务（开机自启、崩溃自拉）**

把下面内容保存为 `/etc/systemd/system/5echm-search.service`（记得把 `<用户名>` 换成你自己的）：

```ini
[Unit]
Description=5echm query service (self-hosted, for dice bot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<用户名>
WorkingDirectory=/home/<用户名>/5echm-search
Environment=PORT=13000
Environment=DATA_UPDATE_INTERVAL_MS=0
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now 5echm-search
systemctl status 5echm-search --no-pager
```

`DATA_UPDATE_INTERVAL_MS=0` 表示关掉服务自带的自动更新检查（它在国内常因访问 GitHub 失败而刷告警），索引更新改用下面的脚本。

**第 7 步：让骰娘改走本机**

在骰娘宿主的 `.env` 里把自建地址排在列表最前，在线服务留作兜底：

```dotenv
dnddicer_query_base_urls=["http://127.0.0.1:13000", "https://5echmsearch.kagangtuya.top"]
```

重启骰娘后即可用。这样即使自建服务在重启或更新索引的几秒里不可用，查询也会自动回退到在线服务。

**第 8 步：别把它暴露到公网（必做）**

服务默认监听所有网卡、接口无鉴权，而骰娘只需要本机访问，所以请把公网入口关掉。第一项必做，后两项按需加：

```bash
# ① 云厂商安全组：不放行 13000 端口（在云控制台里确认，保持默认不放行即可）
# ② 主机防火墙兜底（Debian/Ubuntu 用 ufw；CentOS/RHEL 换成 firewalld）
sudo ufw deny 13000/tcp

# ③ 验证：在另一台机器上执行，应当超时或被拒绝
curl -m 5 http://<你的服务器公网IP>:13000/api/filters
```

如果你希望更彻底，可以在 `server.js` 末尾把 `app.listen(PORT, …)` 改成 `app.listen(PORT, process.env.HOST || "127.0.0.1", …)`，让服务只监听本机（注意：升级源码后需要重新改这一处）。

**第 9 步：索引更新**

内容库大约 1~3 个月更新一次。把下面脚本存为 `~/5echm-search/update-data.sh`，`chmod +x` 之后手动跑或加进定时任务（每月一次足够）：

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
curl -fsSL --retry 3 -o data.js.new "https://5echmsearch.kagangtuya.top/data.js"
[ "$(stat -c%s data.js.new)" -gt 55000000 ] || { echo "体积异常，放弃"; rm -f data.js.new; exit 1; }
head -c 200 data.js.new | grep -q "var contents = new Array" || { echo "格式异常，放弃"; rm -f data.js.new; exit 1; }
mv data.js.new data.js     # 服务监测到文件变化会自动重载，约几秒
```

更新瞬间服务会重建索引，占用的内存会短暂翻倍、期间查询变慢（几秒），建议放在闲聊低谷时执行。

**第 10 步：验收**

```bash
systemctl is-active 5echm-search                                    # active
curl -s http://127.0.0.1:13000/api/filters | head -c 100            # 返回分类 JSON
ps -o rss= -p "$(pgrep -f 'node server.js')" | awk '{print $1/1024" MB"}'   # 常驻内存
```

## 方案二：2GB 内存，补丁版 + swap

2GB 机器可以跑，但要压两件事：**内存占用**和**没有 swap 的缓冲**。先说清楚前提：如果这台机器已经跑着骰娘（协议端就很吃内存），**请先看 `free -h` 的 available——不足 1GB 就别在这台上折腾**，直接用默认在线服务；确有余量再按下面做。

做法三步：

```bash
# ① 给查询服务打个补丁：建索引时只保留英文数字 token（检索只用它们，中文 token 从不被查、只白占内存）
cd ~/5echm-search
curl -fsSL "https://cdn.jsdelivr.net/gh/DND5eChm/5echmweb_search@main/server.js" -o server.js.orig
#    打开 server.js，找到 extractTokens 函数末尾的 .filter((segment) => segment.length >= MIN_TOKEN_LENGTH);
#    在它下面补一行：
#      .filter((segment) => ASCII_TOKEN_REGEX.test(segment));
#    （即：只把 ASCII token 写进倒排索引；中文关键词仍按原逻辑全文扫描，结果不变）

# ② 加 1GB swap（一次性，防索引加载/更新瞬间被系统 OOM 杀掉）
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# ③ 其余步骤与方案一相同（第 2~10 步）
```

打补丁后实测（同样的 62MB 索引）：常驻内存约 246MB、加载/更新瞬间峰值约 590MB，比不打补丁（385MB / 约 950MB）分别省三成以上，检索结果逐条一致。2GB 机器上按「246MB 常驻 + swap 兜底峰值」即可安稳运行；更新索引尽量选低峰，或先 `systemctl restart` 再更新（重启路径峰值更低）。

## 常见问题

**首次启动一直没动静，或日志报下载失败？** 服务在下载约 60MB 的索引，按带宽需要几十秒到两三分钟；若是下载地址不可达，改用第 4 步的手动下载，再把 `data.js` 放进服务目录。

**`node -v` 版本低于 18？** 用 NodeSource 源或官网二进制安装后重试；版本过低会在启动时报语法错误。

**13000 端口被占用？** 换一个端口（改 systemd 里的 `PORT`），插件配置里的地址同步改。

**更新索引之后查询卡了几秒？** 正常：服务在重建索引（期间内存短暂翻倍），几秒后恢复。

**怎么确认骰娘真的走了自建？** 关掉自建服务试一次查询——若仍能返回结果、且是回退行为（稍慢），说明列表里配置生效；也可以看自建服务的进程内存是否被访问时波动。最直接的验证是把自建地址放在列表首位后，查询延迟从公网的百毫秒级降到本机的几十毫秒。

**不用了怎么卸载？** `sudo systemctl disable --now 5echm-search`、删除 `/etc/systemd/system/5echm-search.service` 与 `~/5echm-search` 目录、把插件的 `dnddicer_query_base_urls` 改回在线地址、按需关掉 swap（`sudo swapoff /swapfile` 并删掉 `/etc/fstab` 里那一行）。

## 上游项目与致谢

本页部署的是社区开源项目 [5echmweb_search](https://github.com/DND5eChm/5echmweb_search)（MIT 许可），它负责索引加载与检索接口；索引内容来自《5e不全书》项目，版权归原权利方与翻译者所有。本插件只使用它的接口，不分发其内容文件——索引由你按本页步骤自行下载。
