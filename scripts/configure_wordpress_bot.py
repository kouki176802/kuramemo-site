from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOCKER = Path("/Applications/Docker.app/Contents/Resources/bin/docker")


def upsert_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    output: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if output and output[-1]:
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    if not DOCKER.exists():
        raise SystemExit("Docker Desktopが見つかりません")
    env = os.environ.copy()
    env["DOCKER_CONFIG"] = str(ROOT / "config" / "docker-anonymous")
    env["DOCKER_HOST"] = f"unix://{Path.home()}/.docker/run/docker.sock"
    command = [
        str(DOCKER), "compose", "--env-file", str(ROOT / ".env.wordpress"),
        "-f", str(ROOT / "docker-compose.wordpress.yml"), "--profile", "tools",
        "run", "--rm", "wpcli", "wp", "user", "application-password", "create",
        "kuramemo_owner", "kuramemo-bot", "--porcelain",
    ]
    result = subprocess.run(command, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    password = result.stdout.strip().splitlines()[-1].replace(" ", "")
    if not password:
        raise SystemExit("Application Passwordを取得できませんでした")
    upsert_env(ROOT / ".env", {
        "WORDPRESS_BASE_URL": "http://127.0.0.1:8080",
        "WORDPRESS_USERNAME": "kuramemo_owner",
        "WORDPRESS_APPLICATION_PASSWORD": password,
    })
    print("WordPress投稿BOTの接続情報をGit管理外の.envへ設定しました")


if __name__ == "__main__":
    main()
