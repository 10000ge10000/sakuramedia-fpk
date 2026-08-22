#!/usr/bin/env python3
"""生成 FnDepot 第三方应用源索引与发布落地页。

由 workflow 的 release job 在创建 Release 后调用，产出 public/ 下四个文件：
fnpack.json（FnDepot V2 应用源）、appstore.json、manifests.json、index.html。

SakuraMedia FPK 是 Docker Compose 应用，镜像本身多架构（amd64/arm64），
FPK 不分架构，因此使用 platform=all + packages.all 的单包形式。

用法：
  python3 scripts/generate-appstore.py \
      --version 1.1.0 --tag v1.1.0 \
      --fpk dist/sakuramedia-1.1.0.fpk \
      --out-dir public

仓库 slug 默认取 GITHUB_REPOSITORY 环境变量（fork 后链接自动正确）。
"""

import argparse
import datetime
import hashlib
import json
import os

APP_NAME = 'sakuramedia'
DISPLAY_NAME = 'SakuraMedia'
ICON_PATH = 'ICON_256.PNG'


def package_fingerprint(path: str) -> dict:
    """计算安装包的 sha256 与字节数（FnDepot 强制校验，必须与真实文件一致）。"""
    h = hashlib.sha256()
    size = 0
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return {'sha256': h.hexdigest(), 'size': size}


def build_fnpack(repo: str, ver: str, tag_name: str, fpk_file: str, pkg_dir: str) -> dict:
    """生成 FnDepot (EWEDLCM/FnDepot) 外部应用源 V2 格式的 fnpack.json。

    apps 键名必须与 FPK manifest 的 appname 完全一致（sakuramedia）；
    run_as/install_type/is_docker 与 manifest 和实际运行方式对齐。

    兼容性说明（实测 FnDepot 0.0.7，2026-08）：JSON 直链源的 _sync_app
    按扁平字段处理，应用节点必须有顶层 version / author|distributor /
    download_url / size，否则分别报『缺少必要字段』『json 源格式无效』
    『缺少 download_url（JSON 直链源必须提供）』；releases/packages 的
    按架构分包结构保留给支持 V2 完整规范的新版客户端。
    """
    fingerprint = package_fingerprint(os.path.join(pkg_dir, fpk_file))
    download_url = f'https://github.com/{repo}/releases/download/{tag_name}/{fpk_file}'
    updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    return {
        'schema_version': '2',
        'source_info': {
            'name': '一万AI分享应用源',
            'author': '一万AI分享',
            'homepage': 'https://space.bilibili.com/59438380',
            'description': '一万AI分享维护的飞牛私有云 NAS 第三方应用源（x86 与 ARM64 双架构）',
        },
        'apps': {
            APP_NAME: {
                'display_name': DISPLAY_NAME,
                'desc': 'SakuraMedia 影片媒体库（飞牛 fnOS 第三方安装包）。'
                        '支持 qBittorrent/Jackett 自动发现、磁力搜索订阅下载、'
                        '媒体库管理与刮削；轻量/完整两种部署模式，数据完整保留升级。'
                        '<br><b>首次登录：</b>登录页"服务器地址"填 <b>http://NAS的IP:38000</b>（注意是 38000 不是 38080），'
                        '账号 yiwan，密码 yiwan123。',
                'platform': ['all'],
                'categories': ['影音娱乐'],
                'icon_url': f'https://raw.githubusercontent.com/{repo}/main/{ICON_PATH}',
                'bug_report_url': f'https://github.com/{repo}/issues',
                'maintainer': 'tinypinglite',
                'maintainer_url': 'https://github.com/tinypinglite/sakuramedia',
                'distributor': '一万AI分享',
                'distributor_url': 'https://space.bilibili.com/59438380',
                # FnDepot 0.0.7 兼容字段（详见函数 docstring）
                'version': ver,
                'author': '一万AI分享',
                'download_url': download_url,
                'sha256': fingerprint['sha256'],
                # 0.0.7 的展示逻辑直接拼 "${size} MB"，顶层用 MB 取整（不足 1MB 按 1 计）；
                # releases/packages 内保持 V2 规范的精确字节数
                'size': max(1, round(fingerprint['size'] / 1048576)),
                'run_as': 'package',
                'install_type': '',
                'is_docker': True,
                'service_port': '38080',
                'releases': {
                    ver: {
                        'changelog': '同步官方后端 v0.4.21、前端 v0.4.13；'
                                     '适配逐站 Torznab 索引器配置；导入前健康探测过滤。',
                        'updated_at': updated_at,
                        'packages': {
                            'all': {
                                'download_url': download_url,
                                'sha256': fingerprint['sha256'],
                                'size': fingerprint['size'],
                            },
                        },
                    },
                },
            },
        },
    }


def build_app_entry(repo: str, ver: str, tag_name: str, fpk_file: str) -> dict:
    return {
        'name': APP_NAME,
        'title': f'{DISPLAY_NAME} (一万AI分享分发版)',
        'version': ver,
        'platform': 'all',
        'author': '一万AI分享',
        'description': 'SakuraMedia 影片媒体库：qBittorrent/Jackett 自动发现、磁力搜索订阅下载、媒体库刮削管理。',
        'icon': f'https://raw.githubusercontent.com/{repo}/main/{ICON_PATH}',
        'download_url': f'https://github.com/{repo}/releases/download/{tag_name}/{fpk_file}',
        'changelog': '同步官方 v0.4.21/v0.4.13；适配 Torznab 索引器；导入前健康探测。'
    }


def build_index_html(repo: str, ver: str, app: dict) -> str:
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>一万AI分享 · 飞牛 NAS 专属应用发布站</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #24292e; line-height: 1.6; background-color: #f6f8fa; }}
        .container {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
        h1 {{ color: #0366d6; margin-top: 0; }}
        .card {{ background: #fafbfc; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .badge {{ background: #28a745; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; vertical-align: middle; }}
        code {{ background: #eef1f4; padding: 4px 8px; border-radius: 6px; font-family: SFMono-Regular, Consolas, monospace; font-size: 14px; word-break: break-all; color: #d73a49; }}
        .btn-group {{ margin-top: 15px; display: flex; gap: 12px; flex-wrap: wrap; }}
        a.btn {{ display: inline-block; background: #0366d6; color: white; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; }}
        a.btn:hover {{ background: #0256b9; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 一万AI分享 · 飞牛 NAS 专属应用发布站</h1>
        <p>欢迎使用一万AI分享专属维护的飞牛私有云应用。</p>

        <div class="card">
            <h3>🎬 SakuraMedia <span class="badge">{ver}</span></h3>
            <p>SakuraMedia 影片媒体库（官方前后端 + fnOS 深度适配，一万AI分享分发）。</p>
            <ul>
                <li><strong>自动发现</strong>：qBittorrent / Jackett 自动识别与集成</li>
                <li><strong>磁力搜索订阅下载</strong>：健康站点自动筛选导入</li>
                <li><strong>双模式</strong>：轻量 / 完整（JoyTag + Qdrant）</li>
                <li><strong>架构通用</strong>：x86_64 与 ARM64 均可安装（Docker 多架构镜像）</li>
            </ul>
            <div class="btn-group">
                <a class="btn" href="{app['download_url']}">📥 下载安装包 (.fpk)</a>
            </div>
        </div>

        <div class="card">
            <h3>📦 FnDepot 第三方应用源</h3>
            <p>在 FnDepot 的【源管理 &rarr; 添加源】中填入下面的地址即可一键安装与更新：</p>
            <p><code>https://{repo.replace('/', '.github.io/')}/fnpack.json</code></p>
        </div>
    </div>
</body>
</html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate FnDepot appstore index files')
    parser.add_argument('--version', required=True, help='FPK 版本号')
    parser.add_argument('--tag', required=True, help='Release tag 名')
    parser.add_argument('--fpk', required=True, help='安装包文件名（sakuramedia-<版本>.fpk）')
    parser.add_argument('--out-dir', default='public', help='输出目录')
    parser.add_argument('--pkg-dir', default='dist', help='安装包所在目录（用于计算 sha256/size）')
    args = parser.parse_args()

    repo = os.environ.get('GITHUB_REPOSITORY', '10000ge10000/sakuramedia-fpk')
    app = build_app_entry(repo, args.version, args.tag, args.fpk)
    fnpack = build_fnpack(repo, args.version, args.tag, args.fpk, args.pkg_dir)
    pages_url = f'https://{repo.replace("/", ".github.io/")}/'

    store_data = {
        'name': '一万AI分享应用源',
        'description': '一万AI分享 飞牛私有云 NAS 第三方应用源',
        'url': pages_url,
        'apps': [app],
    }

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, 'appstore.json'), 'w', encoding='utf-8') as f:
        json.dump(store_data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, 'manifests.json'), 'w', encoding='utf-8') as f:
        json.dump([app], f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, 'fnpack.json'), 'w', encoding='utf-8') as f:
        json.dump(fnpack, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(build_index_html(repo, args.version, app))

    print(f'[OK] 已生成应用源文件至 {args.out_dir}/ (repo={repo}, tag={args.tag})')
    print(f'[OK] FnDepot 源: {pages_url}fnpack.json')


if __name__ == '__main__':
    main()
