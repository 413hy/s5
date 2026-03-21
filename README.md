# s5

### socks5
```
apt update
apt install python3 python3-venv python3-pip hydra -y

python3 -m venv venv
source venv/bin/activate
pip install requests PySocks aiohttp aiohttp aiohttp_socks
```


### warp ipv6 转 ipv4出口
```
warp出栈脚本：wget https://raw.githubusercontent.com/413hy/s5/main/warp/warp.sh
wget https://raw.githubusercontent.com/413hy/s5/main/warp/wgcf
wget https://raw.githubusercontent.com/413hy/s5/main/warp/wireguard-go.tar.gz
tar -xzf wireguard-go-linux-amd64.tar.gz
install -m 0755 wgcf /usr/local/bin/wgcf
install -m 0755 wireguard-go /usr/local/bin/wireguard-go

bash warp.sh 4

wget https://raw.githubusercontent.com/413hy/s5/main/warp/warp.sh
```
```
源：https://lovetoshare.top/archives/40.html
2、解锁脚本
wget https://raw.githubusercontent.com/yirenchengfeng1/warp/main/warp.sh

3、全局双栈网络出口
bash warp.sh d

4、IPv4网络出口
bash warp.sh 4

5、IPv6网络出口
bash warp.sh 6
```
