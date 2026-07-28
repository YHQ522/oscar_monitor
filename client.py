"""管控平台 - 客户端（纯连接模式）"""
import sys
import argparse
import webview

parser = argparse.ArgumentParser(description='管控平台客户端')
parser.add_argument('--server', type=str, required=True, help='服务端地址 (如 http://192.168.1.100:5080)')
parser.add_argument('--title', type=str, default='管控平台', help='窗口标题')
args = parser.parse_args()

webview.create_window(args.title, args.server, width=1200, height=800, min_size=(800, 600))
webview.start()
