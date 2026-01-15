# s5

### socks5
```
apt update
apt install python3 python3-venv python3-pip -y

python3 -m venv venv
source venv/bin/activate
pip install requests PySocks
apt install hydra python3-pip -y
```


### warp ipv6 转 ipv4出口
```
bash wgcf.sh
bash wireguard-go.sh
bash warp.sh 4
```
