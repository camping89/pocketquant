"""Health check script for development environment."""

import asyncio
import json
import subprocess
import sys

from rich.console import Console
from rich.table import Table

console = Console(force_terminal=True, legacy_windows=False)


async def check_mongodb() -> tuple[bool, str]:
    from pocketquant.core.config import get_settings
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

    settings = get_settings()
    url = str(settings.mongodb_url)
    host = f"{url.split('@')[-1].split('/')[0]}" if "@" in url else url.split("//")[-1].split("/")[0]
    try:
        client = AsyncMongoClient(url, serverSelectionTimeoutMS=2000)
        info = await client.server_info()
        await client.close()
        return True, f"v{info.get('version', '?')} @ {host}"
    except Exception as e:
        return False, str(e)


async def check_redis() -> tuple[bool, str]:
    import redis.asyncio as redis
    from pocketquant.core.config import get_settings

    settings = get_settings()
    url = str(settings.redis_url)
    host = url.split("//")[-1].split("/")[0]
    try:
        client = redis.from_url(url, socket_timeout=2)
        info = await client.info("server")
        await client.aclose()
        return True, f"v{info.get('redis_version', '?')} @ {host}"
    except Exception as e:
        return False, str(e)


def check_docker_containers() -> list[tuple[str, bool, str]]:
    results = []
    try:
        proc = subprocess.run(
            ["docker", "compose", "-f", "docker/compose.yml", "ps", "--format", "json"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return [("docker-compose", False, proc.stderr.strip() or "compose command failed")]

        for line in proc.stdout.strip().split("\n"):
            if not line:
                continue
            c = json.loads(line)
            name = c.get("Name", "unknown")
            health = c.get("Health", "")
            state = c.get("State", "unknown")
            ports = c.get("Publishers", [])
            port_str = ", ".join(f":{p['PublishedPort']}" for p in ports if p.get("PublishedPort")) if ports else ""
            ok = health == "healthy" or (health == "" and state == "running")
            detail = f"{state}{f' ({health})' if health else ''}{f' [{port_str}]' if port_str else ''}"
            results.append((name, ok, detail))
    except FileNotFoundError:
        results.append(("docker", False, "not installed"))
    except Exception as e:
        results.append(("docker", False, str(e)))
    return results


async def main() -> int:
    console.print("\n[bold]PocketQuant Environment Check[/]\n")

    table = Table(show_header=True, header_style="bold cyan", padding=(0, 1))
    table.add_column("Status", width=4, justify="center")
    table.add_column("Check", min_width=20)
    table.add_column("Details")

    all_ok = True

    for name, ok, detail in check_docker_containers():
        table.add_row("✓" if ok else "✗", f"[white]{name}[/]", detail)
        all_ok &= ok

    table.add_section()

    mongo_ok, mongo_detail = await check_mongodb()
    table.add_row("✓" if mongo_ok else "✗", "[white]MongoDB[/]", mongo_detail)
    all_ok &= mongo_ok

    redis_ok, redis_detail = await check_redis()
    table.add_row("✓" if redis_ok else "✗", "[white]Redis[/]", redis_detail)
    all_ok &= redis_ok

    console.print(table)
    console.print(f"\n[bold {'green' if all_ok else 'red'}]{'All checks passed' if all_ok else 'Some checks failed'}[/]\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
