#!/bin/sh
set -eu

model=/data/lib/joytag/model_vit_768.onnx
expected=8b9b2f12e2c656d9bbe0bf695cd4716d29e10a86a30bb95568c9890a23e9e46c
url=https://github.com/tinypinglite/sakuramediabe/releases/download/model/model_vit_768.onnx
mkdir -p "$(dirname "$model")"

python - "$model" "$expected" "$url" <<'PY'
import hashlib
import os
import sys
import urllib.request

target, expected, url = sys.argv[1:]

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

if not os.path.isfile(target) or sha256(target) != expected:
    temporary = target + ".download"
    try:
        if os.path.exists(temporary):
            os.unlink(temporary)
        with urllib.request.urlopen(url, timeout=120) as response, open(temporary, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        if sha256(temporary) != expected:
            raise RuntimeError("JoyTag 模型 SHA-256 校验失败")
        os.replace(temporary, target)
    except Exception as exc:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise SystemExit(f"JoyTag 模型下载失败：{exc}")
PY

exec python -m joytag_infer
